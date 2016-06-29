from gi.repository import GObject, Gtk

from conga.constants import TAB_ALBUMS, TAB_ARTISTS, TAB_PLAYLISTS, TAB_TRACKS


class CongaHeaderBar(GObject.GObject):
    __gsignals__ = {
        'button-clicked': (GObject.SIGNAL_RUN_FIRST, None, (int,)),
        'search-clicked': (GObject.SIGNAL_RUN_FIRST, None, ()),
    }

    def __init__(self, win):
        GObject.GObject.__init__(self)

        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)

        builder = Gtk.Builder()
        builder.add_from_file('data/headerbar.ui')
        builder.connect_signals(self)

        headerbar.pack_start(builder.get_object('button_hb_back'))
        headerbar.pack_end(builder.get_object('button_hb_search'))

        buttonbox = builder.get_object('hb_buttonbox')
        headerbar.set_custom_title(buttonbox)

        win.set_titlebar(headerbar)

    def on_button_hb_albums_clicked(self, *args):
        self.emit('button-clicked', TAB_ALBUMS)

    def on_button_hb_artists_clicked(self, *args):
        self.emit('button-clicked', TAB_ARTISTS)

    def on_button_hb_tracks_clicked(self, *args):
        self.emit('button-clicked', TAB_TRACKS)

    def on_button_hb_back_clicked(self, *args):
        pass

    def on_button_hb_playlists_clicked(self, *args):
        self.emit('button-clicked', TAB_PLAYLISTS)

    def on_button_hb_search_clicked(self, button):
        self.emit('search-clicked')
