#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
import sys
import os
import numpy
import collections
import subprocess
from enum import IntEnum, auto
from pyzbar.pyzbar import decode
from PIL import Image

def contains_color(img, bgr):
    rows, cols, _ = img.shape
    for i in range(rows):
        for j in range(cols):
            if (img[i, j] == bgr).all():
                return True
    return False

class Pos(IntEnum):
    CENTER      = 0
    TOP         = 1
    RIGHT       = 2
    BTM         = 3
    LEFT        = 4
    TOP_LEFT    = 5
    TOP_RIGHT   = 6
    BTM_RIGHT   = 7
    BTM_LEFT    = 8

    def is_corner(self):
        return self == Pos.TOP_LEFT or self == Pos.TOP_RIGHT or self == Pos.BTM_LEFT or self == Pos.BTM_RIGHT

    def is_edge(self):
        return self == Pos.TOP or self == Pos.BTM or self == Pos.LEFT or self == Pos.RIGHT

def get_top(img):
    return img[0]

def get_bottom(img):
    return img[-1]

def get_left(img):
    return img[:, 1]

def get_right(img):
    return img[:, -1]

class Matcher:
    def __init__(self, bg_color):
        self.bg_color = bg_color

    def check_next(self, img1, img2):
        pos1, pos2 = (self.get_pos(img1), self.get_pos(img2))
        if (pos1.is_corner() and pos2.is_corner()) or (pos1.is_edge() and pos2.is_edge()):
            return (None, None)
        for pos in [Pos.TOP, Pos.BTM, Pos.LEFT, Pos.RIGHT]:
            is_next, rotated = self.get_next_part(img1, img2, pos)
            if is_next:
                return (pos, rotated)
        return (None, None)

    def get_pos(self, img):
        rows, cols, _ = img.shape

        top    = (get_top(img) == self.bg_color).all()
        bottom = (get_bottom(img) == self.bg_color).all()
        left   = (get_left(img) == self.bg_color).all()
        right  = (get_right(img) == self.bg_color).all()

        if top and left:
            return Pos.TOP_LEFT
        elif top and right:
            return Pos.TOP_RIGHT
        elif bottom and left:
            return Pos.BTM_LEFT
        elif bottom and right:
            return Pos.BTM_RIGHT
        elif top:
            return Pos.TOP
        elif bottom:
            return Pos.BTM
        elif left:
            return Pos.LEFT
        elif right:
            return Pos.RIGHT
        else:
            return Pos.CENTER

    def get_next_part(self, img1, img2, pos):
        for r in range(4):
            rotated = numpy.rot90(img2, k=r)
            if pos == Pos.TOP and self.is_continuous(get_top(img1), get_bottom(rotated)):
                return (True, rotated)
            elif pos == Pos.BTM and self.is_continuous(get_bottom(img1), get_top(rotated)):
                return (True, rotated)
            elif pos == Pos.LEFT and self.is_continuous(get_left(img1), get_right(rotated)):
                return (True, rotated)
            elif pos == Pos.RIGHT and self.is_continuous(get_right(img1), get_left(rotated)):
                return (True, rotated)
        return (False, None)

    # edge1: 1xn
    # edge2: 1xn
    def is_continuous(self, edge1, edge2):
        return (not (edge1 == self.bg_color).all()) and (edge1 == edge2).all()

def cat_parts(img1, img2, pos):
    if pos == Pos.TOP:
        return cv2.vconcat([rotated, img1])
    elif pos == Pos.BTM:
        return cv2.vconcat([img1, rotated])
    elif pos == Pos.LEFT:
        return cv2.hconcat([rotated, img1])
    elif pos == Pos.RIGHT:
        return cv2.hconcat([img1, rotated])

def split_parts(png_files, color):
    parts = []

    for png in png_files:
        img = cv2.imread(png, cv2.IMREAD_UNCHANGED)
        print("splitting {0}".format(png))
        for i in range(3):
            for j in range(3):
                splitted = img[(82*i):(82*(i+1)), (82*j):(82*(j+1))]

                if contains_color(splitted, color):
                    # TODO: split png files just once and write them down
                    #cv2.imwrite("out-{0}x{1}-{2}".format(i, j, png), splitted)
                    parts.append(splitted)
    return parts

def rotate_corner(matcher, corner, pos):
    # clock-wise rotation: axes=(1, 0)
    return numpy.rot90(corner, k=((pos - matcher.get_pos(corner))), axes=(1, 0))

def make_whole_image(qr_arr):
    rows = []
    for i in range(3):
        rows.append(cv2.vconcat([qr_arr[i][0], qr_arr[i][1], qr_arr[i][2]]))
    return cv2.hconcat([rows[0], rows[1], rows[2]])

def concat_parts(parts, color):
    matcher = Matcher(color)

    corner = None
    for i in range(len(parts)):
        if matcher.get_pos(parts[i]).is_corner():
            corner = parts.pop(i)
            break

    qr_arr = [[None, None, None], [None, None, None], [None, None, None]]
    qr_arr[0][0] = rotate_corner(matcher, corner, Pos.TOP_LEFT)

    target = (0, 0)


    while len(parts) > 1:
        for n in range(len(parts)):
            part = parts[n]

            (i, j) = target
            #print("n={0} len(parts)={1} target={2}".format(n, len(parts), target))

            pos, rotated = matcher.check_next(qr_arr[i][j], part)
            if pos == None:
                continue
            else:
                if pos == Pos.TOP:
                    j -= 1
                elif pos == Pos.BTM:
                    j += 1
                elif pos == Pos.LEFT:
                    i -= 1
                elif pos == Pos.RIGHT:
                    i += 1

                if (1, 1) == (i, j):
                    continue

                parts.pop(n)
                qr_arr[i][j] = rotated
                #print("found:", (i, j))
                target = (i, j)
                break

    _, rotated = matcher.check_next(qr_arr[0][1], parts[0])
    qr_arr[1][1] = rotated

    return make_whole_image(qr_arr)

def create_qr_image(png_files, color):
    parts = split_parts(png_files, color)
    if len(parts) == 9:
        print("[+] Done!")
    else:
        print("[-] Failed to split")
        sys.exit(1)

    return concat_parts(parts, color)

def get_qr_text(filename):
    data = decode(Image.open(filename))
    return data[0][0].decode('utf-8', 'ignore')

def qubic_rube(dir, code):
    os.chdir(dir)

    subprocess.call(["wget", "http://qubicrube.pwn.seccon.jp:33654/images/" + code + "_U.png"])
    subprocess.call(["wget", "http://qubicrube.pwn.seccon.jp:33654/images/" + code + "_R.png"])
    subprocess.call(["wget", "http://qubicrube.pwn.seccon.jp:33654/images/" + code + "_L.png"])
    subprocess.call(["wget", "http://qubicrube.pwn.seccon.jp:33654/images/" + code + "_F.png"])
    subprocess.call(["wget", "http://qubicrube.pwn.seccon.jp:33654/images/" + code + "_B.png"])
    subprocess.call(["wget", "http://qubicrube.pwn.seccon.jp:33654/images/" + code + "_D.png"])

    png_files = []
    for path in os.listdir("."):
        _, ext = os.path.splitext(path)
        if ext == '.png':
            png_files.append(path)

    for i, color in enumerate(colors):
        qr_img = create_qr_image(png_files, color)
        qr_filename = "qr-{0}.png".format(i)
        cv2.imwrite(qr_filename, qr_img)

        qr_text = get_qr_text(qr_filename)

        if qr_text.startswith("http://"):
            os.chdir("..")
            return qr_text.split("/")[-1]

        if qr_text.startswith("SECCON{"):
            print("Flag is: " + qr_text)
            sys.exit(0)

if __name__ == '__main__':
    YELLOW  = [  0, 213, 255]
    BLUE    = [186,  81,   0]
    GREEN   = [ 96, 158,   0]
    ORANGE  = [  0,  88, 255]
    RED     = [ 58,  30, 196]
    WHITE   = [255, 255, 255]
    colors  = [YELLOW, BLUE, GREEN, ORANGE, RED, WHITE]

    next_code = "01000000000000000000" # 1
    #next_code = "30468d9272ca9219655a" # 30
    #next_code = "3142aec6cd75d8596295" # 31

    for i in range(1, 51):
        os.mkdir(str(i))
        next_code = qubic_rube(str(i), next_code)

    #cv2.waitKey(0)
    #cv2.destroyAllWindows()
