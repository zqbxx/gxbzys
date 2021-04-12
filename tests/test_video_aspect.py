from unittest import TestCase
from unittest.mock import patch
import os
os.environ["PATH"] += os.pathsep + '../'
from gxbzys.smpv import SMPV, VideoAspects


class TestVideo_aspect(TestCase):

    @patch('gxbzys.smpv.SMPV')
    def test_add(self, mpv_instance):
        video_aspect = self.create_video_aspect(mpv_instance)
        assert len(video_aspect.predefined) == 3
        assert video_aspect.predefined[0].w == 4
        assert video_aspect.predefined[0].h == 3
        assert video_aspect.predefined[1].w == 16
        assert video_aspect.predefined[1].h == 9
        assert video_aspect.predefined[2].w == 2.35
        assert video_aspect.predefined[2].h == 1

    @patch('gxbzys.smpv.SMPV')
    def test_current_index(self, mpv_instance):
        video_aspect = self.create_video_aspect(mpv_instance)
        mpv_instance.video_params = {
            'w': 1080,
            'h': 606,
            'dw': 1080,
            'dh': 607
        }
        assert video_aspect.get_current_aspect_index() == 1
        mpv_instance.video_params = {
            'w': 1080,
            'h': 606,
            'dw': 1080,
            'dh': 809
        }
        assert video_aspect.get_current_aspect_index() == 0
        mpv_instance.video_params = {
            'w': 1080,
            'h': 606,
            'dw': 1424,
            'dh': 606
        }
        assert video_aspect.get_current_aspect_index() == 2
        mpv_instance.video_params = {
            'w': 1080,
            'h': 606,
            'dw': 1080,
            'dh': 612
        }
        assert video_aspect.get_current_aspect_index() == 1
        mpv_instance.video_params = {
            'w': 1080,
            'h': 606,
            'dw': 1080,
            'dh': 613
        }
        assert video_aspect.get_current_aspect_index() == -1

    def create_video_aspect(self, mpv_instance):
        video_aspect = VideoAspects(mpv_instance)
        video_aspect.add_predefined_aspect(4, 3)
        video_aspect.add_predefined_aspect(16, 9)
        video_aspect.add_predefined_aspect(4, 3)
        video_aspect.add_predefined_aspect(2.35, 1)
        return video_aspect
