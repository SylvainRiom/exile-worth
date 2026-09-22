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
