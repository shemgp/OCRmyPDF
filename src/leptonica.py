#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# © 2013-14: jbarlow83 from Github (https://github.com/jbarlow83)
#
#
# Lightweight ctypes wrapper for Leptonica image processing library, to
# support OCRmyPDF.

from __future__ import print_function, absolute_import, division
import argparse
import ctypes as C
import sys
import os
from tempfile import TemporaryFile


def stderr(*objs):
    """Python 2/3 compatible print to stderr.
    """
    print("leptonica.py:", *objs, file=sys.stderr)


from ctypes.util import find_library
lept_lib = find_library('lept')
if not lept_lib:
    stderr("Could not find the Leptonica library")
    sys.exit(3)
try:
    lept = C.cdll.LoadLibrary(lept_lib)
except Exception:
    stderr("Could not load the Leptonica library from %s", lept_lib)
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
        ("w", C.c_uint32),                      # width (pixels)
        ("h", C.c_uint32),                      # height (pixels)
        ("d", C.c_uint32),                      # bit depth
        ("wpl", C.c_uint32),                    # 32-bit words per line
        ("refcount", C.c_uint32),               # refcount
        ("xres", C.c_int32),                    # horiz pixels per inch
        ("yres", C.c_int32),                    # vertical pixels per inch
        ("informat", C.c_int32),                # input file format
        ("text", C.POINTER(C.c_char)),          # associated text string
        ("colormap", C.POINTER(_PIXCOLORMAP)),  # color palette or NULL
        ("data", C.POINTER(C.c_uint32))         # raw data
    ]


PIX = C.POINTER(_PIX)

lept.pixDestroy.argtypes = [C.POINTER(PIX)]
lept.pixDestroy.restype = None


def PIX__del__(self):
    """Destroy a pix object.

    Let Python's garbage collector figure out when to call pixDestroy().
    Leptonica implements its own reference counting; pixDestroy decrements the
    reference count if a duplicate object exists.

    Function signature is pixDestroy(struct Pix **), hence C.byref() is used
    to pass the address of the pointer.

    """
    lept.pixDestroy(C.byref(self))

PIX.__del__ = PIX__del__

# I/O
lept.pixRead.argtypes = [C.c_char_p]
lept.pixRead.restype = PIX
lept.pixWriteImpliedFormat.argtypes = [C.c_char_p, PIX, C.c_int32, C.c_int32]
lept.pixWriteImpliedFormat.restype = C.c_int32

# Conversion/thresholding
lept.pixConvertTo1.argtypes = [PIX, C.c_int32]
lept.pixConvertTo1.restype = PIX
lept.pixConvertTo8.argtypes = [PIX, C.c_int32]
lept.pixConvertTo8.restype = PIX
lept.pixOtsuThreshOnBackgroundNorm.argtypes = [
    PIX, PIX,
    C.c_int32, C.c_int32, C.c_int32, C.c_int32, C.c_int32, C.c_int32, C.c_int32,
    C.c_float, C.POINTER(C.c_int32)]
lept.pixOtsuThreshOnBackgroundNorm.restype = PIX
lept.pixSobelEdgeFilter.argtypes = [PIX, C.c_int32]
lept.pixSobelEdgeFilter.restype = PIX
lept.pixInvert.argtypes = [PIX, PIX]
lept.pixInvert.restype = PIX
lept.pixUnsharpMasking.argtypes = [PIX, C.c_int32, C.c_float]
lept.pixUnsharpMasking.restype = PIX

# Resampling
lept.pixScale.argtypes = [PIX, C.c_float, C.c_float]
lept.pixScale.restype = PIX
lept.pixBlockconv.argtypes = [PIX, C.c_int32, C.c_int32]
lept.pixBlockconv.restype = PIX

# Skew
lept.pixDeskew.argtypes = [PIX, C.c_int32]
lept.pixDeskew.restype = PIX

# Orientation
lept.pixOrientDetectDwa.argtypes = [
    PIX, C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_int32, C.c_int32]
lept.pixOrientDetectDwa.restype = C.c_int32
lept.pixMirrorDetectDwa.argtypes = [
    PIX, C.POINTER(C.c_float), C.c_int32, C.c_int32]
lept.pixMirrorDetectDwa.restype = C.c_int32
lept.makeOrientDecision.argtypes = [
    C.c_float, C.c_float, C.c_float, C.c_float, C.POINTER(C.c_int32), C.c_int32]
lept.makeOrientDecision.restype = C.c_int32

# Orthogonal rotation
lept.pixRotateOrth.argtypes = [PIX, C.c_int32]
lept.pixRotateOrth.restype = PIX
lept.pixFlipLR.argtypes = [PIX, PIX]
lept.pixFlipLR.restype = PIX

# Version
lept.getLeptonicaVersion.argtypes = []
lept.getLeptonicaVersion.restype = C.c_char_p

TEXT_ORIENTATION = ['UNKNOWN', 'UP', 'LEFT', 'DOWN', 'RIGHT']
TEXT_ORIENTATION_ANGLES = {
    'UNKNOWN': None, 'UP': 0, 'LEFT': 90, 'DOWN': 180, 'RIGHT': 270}
TEXT_ORIENTATION_ARROWS = {
    'UNKNOWN': u'?', 'UP': u'↑', 'LEFT': u'←', 'DOWN': u'↓', 'RIGHT': u'→'}


class LeptonicaErrorTrap(object):

    """Context manager to trap errors reported by Leptonica.

    Leptonica's error return codes are unreliable to the point of being
    almost useless.  It does, however, write errors to stderr provided that is
    not disabled at its compile time.  Fortunately this is done using error
    macros so it is very self-consistent.

    This context manager redirects stderr to a temporary file which is then
    read and parsed for error messages.  As a side benefit, debug messages
    from Leptonica are also suppressed.

    """
    def __init__(self, verbose=False):
        self.verbose = verbose

    def __enter__(self):
        self.tmpfile = TemporaryFile()

        # Save the old stderr, and redirect stderr to temporary file
        self.old_stderr_fileno = os.dup(sys.stderr.fileno())
        os.dup2(self.tmpfile.fileno(), sys.stderr.fileno())
        return

    def __exit__(self, exc_type, exc_value, traceback):
        # Restore old stderr
        os.dup2(self.old_stderr_fileno, sys.stderr.fileno())
        os.close(self.old_stderr_fileno)

        # Get data from tmpfile (in with block to ensure it is closed)
        with self.tmpfile as tmpfile:
            tmpfile.seek(0)  # Cursor will be at end, so move back to beginning
            leptonica_output = tmpfile.read().decode(errors='replace')

        # If there are Python errors, let them bubble up
        if exc_type:
            stderr(leptonica_output)
            return False

        if self.verbose and leptonica_output.strip() != '':
            stderr(leptonica_output)

        # If there are Leptonica errors, wrap them in Python excpetions
        if 'Error' in leptonica_output:
            if 'image file not found' in leptonica_output:
                raise LeptonicaIOError()
            if 'pixWrite: stream not opened' in leptonica_output:
                raise LeptonicaIOError()
            if 'not enough conf to get orientation' in leptonica_output:
                pass
            else:
                raise LeptonicaError(leptonica_output)

        return False


class LeptonicaError(Exception):
    pass


class LeptonicaIOError(LeptonicaError):
    pass


def pixRead(filename):
    """Load an image file into a PIX object.

    Leptonica can load TIFF, PNM (PBM, PGM, PPM), PNG, and JPEG.  If loading
    fails then the object will wrap a C null pointer.

    """

    from PIL import Image
    im = Image.open(filename)
    if im.format == 'PPM':
        # Leptonica's PNM reader is buggy.  If the first pixel looks like a CR or LF,
        # it will get consumed instead of read as image data.
        from tempfile import NamedTemporaryFile

        if im.mode == '1' or im.mode == 'L':
            with NamedTemporaryFile(delete=True, suffix=".tif") as tmpfile:
                im.save(tmpfile.name)
                with LeptonicaErrorTrap():
                    return lept.pixRead(tmpfile.name.encode(sys.getfilesystemencoding()))
        elif im.mode == 'RGB':
            with NamedTemporaryFile(delete=True, suffix=".png") as tmpfile:
                im.save(tmpfile.name)
                with LeptonicaErrorTrap():
                    return lept.pixRead(tmpfile.name.encode(sys.getfilesystemencoding()))
        else:
            raise NotImplementedError(
                "Don't know what to do with %s (format %s)" % (filename, im.format))

    else:
        with LeptonicaErrorTrap():
            return lept.pixRead(filename.encode(sys.getfilesystemencoding()))


def pixConvertTo1(pix, threshold=130):
    """Binarize an image using a fixed global threshold.

    If the image background varies or contrast is not normalized this will
    ruin the image.

    """

    with LeptonicaErrorTrap():
        return lept.pixConvertTo1(pix, threshold)


def pixConvertTo8(pix, colormap=False):
    """Convert color image to grayscale."""

    with LeptonicaErrorTrap():
        return lept.pixConvertTo8(pix, colormap)


def pixOtsuThreshOnBackgroundNorm(pix_source, pix_mask=None, tile_size=(10, 15), threshold=100,
                                  mincount=50, bgval=255, smooth=(2, 2), scorefract=0.1):
    """Binarize an image, accounting for background variation."""

    used_threshold = C.c_int32(0)

    with LeptonicaErrorTrap():
        if pix_source.contents.d > 8:
            pix_source = pixConvertTo8(pix_source)
        elif pix_source.contents.d == 1:
            return pixConvertTo1(pix_source)

        pix_out = lept.pixOtsuThreshOnBackgroundNorm(
            pix_source, pix_mask, tile_size[0], tile_size[1],
            threshold, mincount, bgval, smooth[0], smooth[1], C.c_float(scorefract),
            C.byref(used_threshold))

    return pix_out


def pixSobelEdgeFilter(pix_source):
    """Filter edges in input."""

    with LeptonicaErrorTrap():
        if pix_source.contents.d > 8:
            pix_source = pixConvertTo8(pix_source)

        return lept.pixSobelEdgeFilter(pix_source, C.c_int32(2))    # 2 == horiz+vert edges


def pixInvert(pix):
    """Returns a color-inverted copy of image."""

    with LeptonicaErrorTrap():
        return lept.pixInvert(None, pix)


def pixUnsharpMasking(pix, half_width, fract):
    """Unsharpen the image."""

    wc = C.c_int32(half_width)
    fract = C.c_float(fract)

    with LeptonicaErrorTrap():
        return lept.pixUnsharpMasking(pix, half_width, fract)


def pixScale(pix, scalex, scaley):
    """Returns the pix object rescaled according to the proportions given."""
    with LeptonicaErrorTrap():
        return lept.pixScale(pix, scalex, scaley)


def pixBlockconv(pix, half_width, half_height):
    """Return pix object convoluted by a kernel specified by input dimensions."""

    wc, hc = C.c_int32(half_width), C.c_int32(half_height)

    with LeptonicaErrorTrap():
        return lept.pixBlockconv(pix, wc, hc)


def pixDeskew(pix, reduction_factor=0):
    """Returns the deskewed pix object.

    Leptonica uses the method of differential square sums, which its author
    claim is faster and more robust than the Hough transform used by
    ImageMagick.  Testing found this method is about 30-40x times faster.

    A clone of the original is returned when the algorithm cannot find a skew
    angle with sufficient confidence.  The skew angle is assumed to be no more
    than ±6°.

    reduction_factor -- amount to downsample (0 for default) when searching
        for skew angle

    """
    with LeptonicaErrorTrap():
        return lept.pixDeskew(pix, reduction_factor)


def pixOrientDetectDwa(pix, mincount=0, debug=0):
    """Returns confidence measure that the image is oriented correctly.

    Use makeOrientDecision to let Leptonica translate the confidence
    measurements into the recommended rotation.

    pix - deskewed 1 bpp English text, 150-300 ppi

    """
    up_confidence = C.c_float(0.0)
    left_confidence = C.c_float(0.0)

    with LeptonicaErrorTrap():
        result = lept.pixOrientDetectDwa(
            pix, C.byref(up_confidence), C.byref(left_confidence),
            mincount, debug)
    if result != 0:
        raise LeptonicaError("pixOrientDetectDwa returned {0}".format(result))
    return (up_confidence.value, left_confidence.value)


def makeOrientDecision(confidence, min_up_confidence=0.0, min_ratio=0.0, debug=0):
    """Returns the orientation of text, in counter-clockwise degrees."""

    up_confidence = C.c_float(confidence[0])
    left_confidence = C.c_float(confidence[1])
    orient = C.c_int32(-1)

    with LeptonicaErrorTrap():
        lept.makeOrientDecision(
            up_confidence, left_confidence, min_up_confidence,
            min_ratio, C.byref(orient), debug)
    assert 0 <= orient.value < len(TEXT_ORIENTATION)

    orientation = TEXT_ORIENTATION[orient.value]
    return TEXT_ORIENTATION_ANGLES[orientation]


def pixRotateOrth(pix, degrees_clockwise):
    """Returns the input rotated by 90, 180, or 270 degrees clockwise.

    Since makeOrientDecision() returns counter-clockwise degrees, its value
    may be passed directly to this function.

    pix -- all bit depths
    degrees_clockwise -- 0, 90, 180, 270 accepted

    """

    if degrees_clockwise is None:
        return pix  # No rotation

    if degrees_clockwise % 90 != 0:
        raise ValueError("degrees_clockwise be a multiple of 90 degrees")

    quads = int(degrees_clockwise // 90)
    if not quads in range(0, 4):
        raise ValueError("degrees_clockwise must not exceed 360 degrees")

    with LeptonicaErrorTrap():
        return lept.pixRotateOrth(pix, quads)


def pixMirrorDetectDwa(pix, mincount=0, debug=0):
    """Returns confidence that image is correct (>0) or mirrored (<0).

    It is not necessary to check for up-down flipping, since an orientation
    check will correct that as well.

    Obviously mirroring is only an issue for scanned microfiche, film, etc.

    A value of -5.0 is high confidence that the image is mirrored.

    """
    mirror_confidence = C.c_float(0.0)

    with LeptonicaErrorTrap():
        result = lept.pixMirrorDetectDwa(
            pix, C.byref(mirror_confidence),
            mincount, debug)
    if result != 0:
        raise LeptonicaError("pixMirrorDetectDwa returned {0}".format(result))
    return mirror_confidence.value


def pixFlipLR(pix):
    """Returns a left-right flipped copy of the image."""

    with LeptonicaErrorTrap():
        return lept.pixFlipLR(None, pix)


def pixWriteImpliedFormat(filename, pix, jpeg_quality=0, jpeg_progressive=0):
    """Write pix to the filename, with the extension indicating format.

    jpeg_quality -- quality (iff JPEG; 1 - 100, 0 for default)
    jpeg_progressive -- (iff JPEG; 0 for baseline seq., 1 for progressive)

    """
    fileroot, extension = os.path.splitext(filename)
    fix_pnm = False
    if extension.lower() in ('.pbm', '.pgm', '.ppm'):
        # Leptonica does not process handle these extensions correctly, but
        # does handle .pnm correctly.  Add another .pnm suffix.
        filename += '.pnm'
        fix_pnm = True

    with LeptonicaErrorTrap():
        lept.pixWriteImpliedFormat(
            filename.encode(sys.getfilesystemencoding()),
            pix, jpeg_quality, jpeg_progressive)

    if fix_pnm:
        from shutil import move
        move(filename, filename[:-4])   # Remove .pnm suffix


def getLeptonicaVersion():
    """Get Leptonica version string.

    Caveat: Leptonica expects the caller to free this memory.  We don't,
    since that would involve binding to libc to access libc.free(),
    a pointless effort to reclaim 100 bytes of memory.

    """
    return lept.getLeptonicaVersion().decode()


def deskew(args):
    try:
        pix_source = pixRead(args.infile)
    except LeptonicaIOError:
        stderr("Failed to open file: %s" % args.infile)
        sys.exit(2)

    if args.dpi < 150:
        reduction_factor = 1  # Don't downsample too much if DPI is already low
    else:
        reduction_factor = 0  # Use default
    pix_deskewed = pixDeskew(pix_source, reduction_factor)

    try:
        pixWriteImpliedFormat(args.outfile, pix_deskewed)
    except LeptonicaIOError:
        stderr("Failed to open destination file: %s" % args.outfile)
        sys.exit(5)


def orient(args):
    """Fix image left/right/up/down/mirror orientation problems."""
    try:
        pix = pixRead(args.infile)
    except LeptonicaIOError:
        stderr("Failed to open file: %s" % args.infile)
        sys.exit(2)

    pix1 = pixOtsuThreshOnBackgroundNorm(pix)

    confidence = pixOrientDetectDwa(pix1)
    decision = makeOrientDecision(confidence)
    if args.verbose:
        stderr("orient: confidence {0}, decision {1}".format(confidence, decision))

    if args.check:
        if decision is None:
            stderr("Warning: could not determine orientation of %s" %
                   args.infile)
        elif decision != 0:
            stderr(
                "Warning: {0} probably oriented with text facing {1} degrees CCW".format(
                args.infile, decision))
        sys.exit(0)

    if decision is None:
        stderr("Warning: could not determine orientation of %s" %
               args.infile)
        sys.exit(0)

    pix_oriented = pixRotateOrth(pix, decision)

    if args.mirror:
        pix1_oriented = pixOtsuThreshOnBackgroundNorm(pix_oriented)
        mirror_confidence = pixMirrorDetectDwa(pix1_oriented)
        if args.verbose:
            stderr("orient: mirror confidence {0}".format(mirror_confidence))
        if mirror_confidence < -5.0:
            pix_oriented = pixFlipLR(pix_oriented)

    try:
        pixWriteImpliedFormat(args.outfile, pix_oriented)
    except LeptonicaIOError:
        stderr("Failed to open destination file: %s" % args.outfile)
        sys.exit(5)


def binarize(args):
    """Binarize image."""
    try:
        pix = pixRead(args.infile)
    except LeptonicaIOError:
        stderr("Failed to open file: %s" % args.infile)
        sys.exit(2)

    pix1 = pixOtsuThreshOnBackgroundNorm(pix)

    try:
        pixWriteImpliedFormat(args.outfile, pix1)
    except LeptonicaIOError:
        stderr("Failed to open destination file: %s" % args.outfile)
        sys.exit(5)


def dot_matrix(args):
    """Perform repair on dot matrix printed image."""
    try:
        pix = pixRead(args.infile)
    except LeptonicaIOError:
        stderr("Failed to open file: %s" % args.infile)
        sys.exit(2)

    # Detect edges (highlight the dots)
    pix_edges = pixInvert(pixSobelEdgeFilter(pix))

    # Threshold
    pix1 = pixConvertTo1(pix_edges, 200)

    # Blur the dots into each other
    pix8 = pixConvertTo8(pix1)
    pix_blur = pixBlockconv(pix8, half_width=3, half_height=2)

    # Sharpen
    pix_unsharp = pixUnsharpMasking(pix_blur, half_width=9, fract=0.8)
    pix_out = pixConvertTo1(pix_unsharp, 160)

    try:
        pixWriteImpliedFormat(args.outfile, pix_out)
    except LeptonicaIOError:
        stderr("Failed to open destination file: %s" % args.outfile)
        sys.exit(5)


def main():
    parser = argparse.ArgumentParser(
        description="Python wrapper to access Leptonica")
    parser.add_argument('-v', '--verbose', action='store_true')

    subparsers = parser.add_subparsers(title='commands',
                                       description='supported operations')

    # leptonica.py deskew
    parser_deskew = subparsers.add_parser('deskew',
                                          help="deskew an image")
    parser_deskew.add_argument('-r', '--dpi', dest='dpi', action='store',
                               type=int, default=300, help='input resolution')
    parser_deskew.add_argument('infile', help='image to deskew')
    parser_deskew.add_argument('outfile', help='deskewed output image')
    parser_deskew.set_defaults(func=deskew)

    # leptonica.py orient
    parser_orient = subparsers.add_parser('orient',
                                          help="correct image orientation")
    parser_orient.add_argument('infile',
                               help="deskewed file to check orientation")
    parser_orient.add_argument('outfile',
                               nargs='?', default=None,
                               help="output file with fixed orientation")
    parser_orient.add_argument('--check',
                               help="only orientation and report problems",
                               action='store_true')
    parser_orient.add_argument('--mirror',
                               help="also check if image may be mirrored",
                               action='store_true')
    parser_orient.set_defaults(func=orient)

    # leptonica.py binarize
    parser_binarize = subparsers.add_parser('binarize',
                                            help='convert image to black/white')
    parser_binarize.add_argument('infile',
                                 help="file to binarize")
    parser_binarize.add_argument('outfile',
                                 nargs='?', default=None,
                                 help="output file")
    parser_binarize.set_defaults(func=binarize)

    # leptonica.py dotmatrix
    parser_dotmatrix = subparsers.add_parser('dotmatrix',
                                             help="connect dots in dot matrix scans")
    parser_dotmatrix.add_argument('infile',
                                  help="file to process")
    parser_dotmatrix.add_argument('outfile',
                                  nargs='?', default=None,
                                  help="output file")
    parser_dotmatrix.set_defaults(func=dot_matrix)

    args = parser.parse_args()

    if getLeptonicaVersion() != u'leptonica-1.69':
        stderr("Unexpected leptonica version: %s" % getLeptonicaVersion())

    args.func(args)

if __name__ == '__main__':
    main()


def _test_output(mode, extension, im_format):
    from PIL import Image
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(prefix='test-lept-pnm', suffix=extension, delete=True) as tmpfile:
        im = Image.new(mode=mode, size=(100, 100))
        im.save(tmpfile, im_format)

        pix = pixRead(tmpfile.name)
        pixWriteImpliedFormat(tmpfile.name, pix)

        im_roundtrip = Image.open(tmpfile.name)
        assert im_roundtrip.mode == im.mode, "leptonica mode differs"
        assert im_roundtrip.format == im_format, \
            "{0}: leptonica produced a {1}".format(
                extension,
                im_roundtrip.format)


def test_pnm_output():
    params = [['1', '.pbm', 'PPM'], ['L', '.pgm', 'PPM'],
              ['RGB', '.ppm', 'PPM']]
    for param in params:
        _test_output(*param)


from contextlib import contextmanager


@contextmanager
def replaced_args(args):
    try:
        saved_args = sys.argv[:]
        sys.argv = [os.path.basename(__file__)] + args
        yield
    finally:
        sys.argv = saved_args


def _test_orient(test_im, test_case=''):
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(prefix="test-orient-", suffix=".tiff", delete=True) as tmpfile:
        test_im.save(tmpfile, "TIFF")

        with replaced_args(['orient', '--check', tmpfile.name]):
            try:
                main()
            except SystemExit as e:
                if e.code != 0:
                    raise e

        with NamedTemporaryFile(prefix="test-orient-fixed-{0}-".format(test_case),
                                suffix=".tiff", delete=True) as outfile:
            with replaced_args(['-v', 'orient', '--mirror', tmpfile.name, outfile.name]):
                try:
                    main()
                except SystemExit as e:
                    if e.code != 0:
                        raise e


def test_orient():
    from PIL import Image

    im = Image.open('test/Picture_003.jpg')

    for color in ['1', 'L', 'RGB']:
        converted = im.convert(mode=color)
        for angle in (0, 90, 180, 270):
            rotated = converted.rotate(angle)
            test_case = "{0}-{1}".format(color, angle)
            _test_orient(rotated, test_case)

            mirrored = rotated.transpose(Image.FLIP_LEFT_RIGHT)
            test_case = "{0}-{1}-LR".format(color, angle)
            _test_orient(mirrored, test_case)


def test_pnm_crlf_bug():
    from tempfile import NamedTemporaryFile

    pnm_header = b"P5\x0A2 2\x0A255\x0A"
    pnm_data = b"\x0A\x00\x0A\x0D"

    with NamedTemporaryFile(prefix="test-pnm-crlf", suffix=".pgm", delete=True) as tmpfile:
        tmpfile.write(pnm_header)
        tmpfile.write(pnm_data)
        tmpfile.flush()
        with LeptonicaErrorTrap():
            pixRead(tmpfile.name)
