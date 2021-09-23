from macast import Renderer


# https://github.com/xfangfang/Macast/wiki/Custom-Renderer
from gxbzys.smpv import SMPV


class YRRenderer(Renderer):

    def __init__(self, player: SMPV):
        super().__init__()
        self.player = player

    def set_media_url(self, url):
        self.player.stop()
        self.player.playlist_clear()
        self.player.playlist_append(url)
        self.player.playlist_pos = 0
        print(url)
