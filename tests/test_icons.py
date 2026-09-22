import unittest

import cv2
import numpy as np

from exile_worth.model import Reason
from exile_worth.icons import IconMatcher
from exile_worth.vision import Profiles, Scanner, SLOTS


def artwork(seed):
    random = np.random.default_rng(seed)
    image = np.zeros((64,64,4),np.uint8)
    for _ in range(18):
        point = tuple(int(v) for v in random.integers(10,54,2))
        colour = tuple(int(v) for v in random.integers(50,250,3)) + (255,)
        cv2.circle(image,point,int(random.integers(3,10)),colour,-1)
    return image


def render(image, size=50, number='254'):
    cell = np.full((51,52,3), (14,9,5), np.uint8)
    icon = cv2.resize(image, (size,size), interpolation=cv2.INTER_AREA)
    x,y = (52-size)//2,(51-size)//2
    alpha = icon[:,:,3:4].astype(float)/255
    cell[y:y+size,x:x+size] = icon[:,:,:3]*alpha+cell[y:y+size,x:x+size]*(1-alpha)
    cv2.putText(cell,number,(2,14),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,0),3,cv2.LINE_AA)
    cv2.putText(cell,number,(2,14),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
    return cell


class IconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = {'transmute':artwork(8), 'greater-orb-of-transmutation':artwork(8),
                      'perfect-orb-of-transmutation':artwork(8), 'divine':artwork(17)}
        cls.matcher = IconMatcher(cls.images)

    def test_scale_background_and_count_do_not_change_identity(self):
        cells = [render(self.images['divine'], size, count)
                 for size,count in [(48,'1'),(50,'864'),(51,'216')]]
        for match in self.matcher.match_many(cells):
            self.assertEqual(match.item,'divine')

    def test_duplicate_artwork_is_a_family_not_arbitrary_variant(self):
        match = self.matcher.match_many([render(self.images['transmute'])])[0]
        self.assertIsNone(match.item)
        self.assertEqual(set(match.alternatives),{'transmute','greater-orb-of-transmutation','perfect-orb-of-transmutation'})

    def test_dark_silhouettes_and_unrelated_images_rejected(self):
        dark = (render(self.images['divine']).astype(float)*.2).astype(np.uint8)
        noise = np.random.default_rng(40).integers(0,255,(51,52,3),dtype=np.uint8)
        for match in self.matcher.match_many([dark,noise,np.zeros((51,52,3),np.uint8)]):
            self.assertIsNone(match.item)
            self.assertFalse(match.alternatives)

    def test_no_calibration_needed_and_quantity_independent_of_icon(self):
        import tempfile
        from pathlib import Path
        class Digits:
            def read(self, image):
                return 254,.99
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), Digits(), self.matcher)
            frame = np.zeros((1080,1920,3),np.uint8)
            for slot in ('L11','L12','L13'):
                x,y,w,h = SLOTS[slot]
                frame[y:y+h,x:x+w] = render(self.images['transmute'])
            readings = {r.slot:r for r in scanner.read(frame)}
            self.assertEqual(readings['L11'].item,'transmute')
            self.assertEqual(readings['L12'].item,'greater-orb-of-transmutation')
            self.assertEqual(readings['L13'].item,'perfect-orb-of-transmutation')
            self.assertEqual(readings['L13'].quantity,254)
            self.assertIsNone(readings['C01'].item)
            self.assertEqual(readings['C01'].quantity,254)

    def test_family_in_wrong_row_does_not_get_invented_tier(self):
        import tempfile
        from pathlib import Path
        class Digits:
            def read(self, image):
                return 20,.99
        with tempfile.TemporaryDirectory() as directory:
            scanner = Scanner(Profiles(Path(directory)), Digits(), self.matcher)
            frame = np.zeros((1080,1920,3),np.uint8)
            x,y,w,h = SLOTS['L21']
            frame[y:y+h,x:x+w] = render(self.images['transmute'])
            reading = next(r for r in scanner.read(frame) if r.slot == 'L21')
            self.assertIsNone(reading.item)
            self.assertEqual(reading.reason,Reason.VARIANT)
