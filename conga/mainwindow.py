import gi
from gi.repository import Gtk

gi.require_version('Gtk', '3.0')


class CongaWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="Hello World")

        self.album_grid = Gtk.Grid()
        self.add(self.album_grid)

        self.connect("delete-event", Gtk.main_quit)

    def add_album(self, album):
        pass
