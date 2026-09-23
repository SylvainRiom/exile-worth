import unittest

import cv2
import numpy as np

from exile_worth.vision import DigitReader


class OCRIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = DigitReader()

    def test_small_white_stack_numbers(self):
        for number in ('1','11','31','254','864','216','1000'):
            with self.subTest(number=number):
                image = np.zeros((18,52,3),np.uint8)
                cv2.putText(image,number,(1,14),cv2.FONT_HERSHEY_SIMPLEX,.5,
                            (255,255,255),1,cv2.LINE_AA)
                quantity,confidence = self.reader.read(image)
                self.assertEqual(quantity,int(number))
                self.assertGreaterEqual(confidence,.9)

    def test_blank_is_unknown_not_zero(self):
        self.assertIsNone(self.reader.read(np.zeros((18,52,3),np.uint8))[0])

    def test_icon_highlights_to_the_right_are_not_extra_digits(self):
        image = np.zeros((18,52,3),np.uint8)
        cv2.putText(image,'254',(1,14),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
        cv2.line(image,(47,5),(47,16),(255,255,255),2)
        self.assertEqual(self.reader.read(image)[0],254)

    def test_outlined_counters_on_coloured_artwork(self):
        from tests.test_icons import artwork, render
        for seed in (8,17,41):
            with self.subTest(seed=seed):
                self.assertEqual(self.reader.read(render(artwork(seed))[:18])[0],254)


class ScriptedOCR:
    """Answers each call with the next (text, confidence): full image, raw crop, clean crop."""
    def __init__(self, *answers):
        self.answers = list(answers)

    def __call__(self, image, **_):
        text, confidence = self.answers.pop(0)
        return [(text, confidence)], None


def scripted_reader(*answers):
    reader = DigitReader.__new__(DigitReader)
    reader.ocr = ScriptedOCR(*answers)
    reader.last_approximate = False
    return reader


def counter():
    image = np.zeros((18,52,3),np.uint8)
    cv2.putText(image,'24.7K',(1,14),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
    return image


class AbbreviatedCounterTests(unittest.TestCase):
    """A K/M suffix seen once must never let a truncated number pass as exact."""

    def test_suffix_below_the_bar_refuses_agreeing_truncated_crops(self):
        reader = scripted_reader(('24.7K', .80), ('247', .97), ('247', .96))
        quantity, _ = reader.read(counter())
        self.assertIsNone(quantity)
        self.assertFalse(reader.last_approximate)

    def test_suffix_seen_by_one_crop_refuses_the_other(self):
        reader = scripted_reader(('', .10), ('24', .95), ('24K', .70))
        self.assertIsNone(reader.read(counter())[0])

    def test_a_crop_that_reads_the_suffix_stays_approximate(self):
        reader = scripted_reader(('24.7K', .80), ('24.7K', .95), ('', 0.0))
        self.assertEqual(reader.read(counter())[0], 24_700)
        self.assertTrue(reader.last_approximate)

    def test_full_read_above_the_bar_is_approximate(self):
        reader = scripted_reader(('24.7K', .95))
        self.assertEqual(reader.read(counter())[0], 24_700)
        self.assertTrue(reader.last_approximate)

    def test_plain_counts_stay_exact(self):
        reader = scripted_reader(('247', .80), ('247', .97), ('247', .96))
        self.assertEqual(reader.read(counter())[0], 247)
        self.assertFalse(reader.last_approximate)

    def test_a_previous_approximate_read_does_not_leak(self):
        reader = scripted_reader(('24.7K', .95), ('', .1), ('247', .97), ('247', .96))
        reader.read(counter())
        reader.read(counter())
        self.assertFalse(reader.last_approximate)

    def test_a_mark_read_as_noise_does_not_refuse_a_clear_count(self):
        """`6M` at 0.38 on the full cell was artwork; both crops read 6."""
        reader = scripted_reader(('6M', .38), ('6', .99), ('6', .99))
        self.assertEqual(reader.read(counter())[0], 6)
        self.assertFalse(reader.last_approximate)
