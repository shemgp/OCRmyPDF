#!/usr/bin/env python2
# -*- coding: utf-8 -*-
##############################################################################
# © 2013-14: jbarlow83 from Github (https://github.com/jbarlow83)
##############################################################################
#
# Use Leptonica to detect find and remove page skew.  Leptonica uses the method
# of differential square sums, which its author claim is faster and more robust
# than the Hough transform used by ImageMagick.

from __future__ import print_function, absolute_import, division
import argparse
import ctypes as C
import sys


def stderr(*objs):
    """Python 2/3 compatible print to stderr.
    """
    print(*objs, file=sys.stderr)


from ctypes.util import find_library
lept_lib = find_library('lept')
if not lept_lib:
    stderr("deskew.py: Could not find the Leptonica library")
    sys.exit(3)
try:
    lept = C.cdll.LoadLibrary(lept_lib)
except Exception:
    stderr("deskew.py: Could not load the Leptonica library from %s", lept_lib)
    sys.exit(3)


class _PIXCOLORMAP(C.Structure):
    """struct PixColormap from Leptonica src/pix.h
    """
    _fields_ = [
        ("array", C.c_void_p),
        ("depth", C.c_int32),
        ("nalloc", C.c_int32),
        ("n", C.c_int32)
    ]


class _PIX(C.Structure):
    """struct Pix from Leptonica src/pix.h
    """
    _fields_ = [
        ("w", C.c_uint32),
        ("h", C.c_uint32),
        ("d", C.c_uint32),
        ("wpl", C.c_uint32),
        ("refcount", C.c_uint32),
        ("xres", C.c_uint32),
        ("yres", C.c_uint32),
        ("informat", C.c_int32),
        ("text", C.POINTER(C.c_char)),
        ("colormap", C.POINTER(_PIXCOLORMAP)),
        ("data", C.POINTER(C.c_uint32))
    ]


PIX = C.POINTER(_PIX)

lept.pixRead.argtypes = [C.c_char_p]
lept.pixRead.restype = PIX
lept.pixScale.argtypes = [PIX, C.c_float, C.c_float]
lept.pixScale.restype = PIX
lept.pixDeskew.argtypes = [PIX, C.c_int32]
lept.pixDeskew.restype = PIX
lept.pixWriteImpliedFormat.argtypes = [C.c_char_p, PIX, C.c_int32, C.c_int32]
lept.pixWriteImpliedFormat.restype = C.c_int32
lept.pixDestroy.argtypes = [C.POINTER(PIX)]
lept.pixDestroy.restype = None


class LeptonicaError(Exception):
    pass


def pixRead(filename):
    """Load an image file into a PIX object.

    Leptonica can load TIFF, PNM (PBM, PGM, PPM), PNG, and JPEG.  If loading
    fails then the object will wrap a C null pointer.

    """
    return lept.pixRead(filename)


def pixScale(pix, scalex, scaley):
    """Returns the pix object rescaled according to the proportions given."""
    return lept.pixScale(pix, scalex, scaley)


def pixDeskew(pix, reduction_factor=0):
    """Returns the deskewed pix object, or a clone of the original.

    reduction_factor -- amount to downsample (0 for default) when searching
        for skew angle

    """
    return lept.pixDeskew(pix, reduction_factor)


def pixWriteImpliedFormat(filename, pix, jpeg_quality=0, jpeg_progressive=0):
    """Write pix to the filename, with the extension indicating format.

    jpeg_quality -- quality (iff JPEG; 1 - 100, 0 for default)
    jpeg_ progressive -- (iff JPEG; 0 for baseline seq., 1 for progressive)

    """
    result = lept.pixWriteImpliedFormat(filename, pix, jpeg_quality,
                                        jpeg_progressive)
    if result != 0:
        # There is no programmatic way to get the cause of the error, but
        # Leptonica will write it to stdout/stderr
        raise LeptonicaError("pixWriteImpliedFormat('%s', ...) returned error"
                             % filename)


def pixDestroy(pix):
    """Destroy the pix object.

    Function signature is pixDestroy(struct Pix **), hence C.byref() to pass
    the address of the pointer.

    """
    lept.pixDestroy(C.byref(pix))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Deskew images with Leptonica")
    parser.add_argument('-r', '--dpi', dest='dpi', action='store_const',
                        const=300, help='input image resolution')
    parser.add_argument('infile', help='image to deskew')
    parser.add_argument('outfile', help='deskewed output image')

    args = parser.parse_args()

    pix_source = pixRead(args.infile)
    if not pix_source:
        stderr("Failed to open file: %s" % args.infile)
        sys.exit(2)

    if args.dpi < 150:
        reduction_factor = 1  # Don't downsample too much if DPI is already low
    else:
        reduction_factor = 0  # Use default
    pix_deskewed = pixDeskew(pix_source, reduction_factor)

    try:
        pixWriteImpliedFormat(args.outfile, pix_deskewed)
    except LeptonicaError as e:
        stderr(e)
        sys.exit(5)
    pixDestroy(pix_source)
    pixDestroy(pix_deskewed)

