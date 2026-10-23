import unittest
from core.hand_motion import HandMotion

class Motion(unittest.TestCase):
    def test_reacquisition_anchors_to_actual_pointer_without_jump(self):
        motion=HandMotion()
        self.assertIsNone(motion.sample(.2,.3,1,(1920,1080),(700,400)))
        moved=motion.sample(.3,.3,1.033,(1920,1080),(700,400))
        self.assertGreater(moved[0],900)
        motion.reset()
        self.assertIsNone(motion.sample(.8,.8,2,(1920,1080),moved))
        self.assertIsNone(motion.sample(.8,.8,2.033,(1920,1080),moved))
        self.assertGreater(motion.sample(.82,.8,2.066,(1920,1080),moved)[0],moved[0])

    def test_fast_movement_tracks_in_one_frame_and_small_jitter_is_filtered(self):
        motion=HandMotion('Balanced');motion.sample(.5,.5,1,(1920,1080),(960,540))
        moved=motion.sample(.6,.5,1.033,(1920,1080),(960,540))
        self.assertGreater(moved[0],1190)
        motion.reset();motion.sample(.5,.5,2,(1920,1080),(960,540))
        self.assertIsNone(motion.sample(.5001,.5,2.033,(1920,1080),(960,540)))

    def test_tracking_warp_reanchors_and_pointer_stays_on_screen(self):
        motion=HandMotion('Fast');motion.sample(.1,.1,1,(1920,1080),(1800,1000))
        self.assertEqual(motion.sample(.3,.3,1.033,(1920,1080),(1800,1000)),(1915,1075))
        self.assertIsNone(motion.sample(.9,.9,1.066,(1920,1080),(1915,1075)))

if __name__=='__main__':unittest.main()
