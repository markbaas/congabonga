import cgi
import random
from collections import defaultdict

from gi.repository import Gdk, GdkPixbuf, GObject, Gtk

from conga import utils
from conga.constants import (TAB_ALBUM_DETAILS, TAB_ARTIST_DETAILS,
                             TAB_ARTISTS, TAB_SEARCH)
from conga.headerbar import CongaHeaderBar


class CongaUi(GObject.GObject):
    __gsignals__ = {
        'tab-changed': (GObject.SIGNAL_RUN_FIRST, None, (int, str)),
        'player-seek': (GObject.SIGNAL_RUN_FIRST, None, (int,)),
        'player-pause': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'player-next': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'player-previous': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'player-play': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        'playlist-activated': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        'artist-activated': (GObject.SIGNAL_RUN_FIRST, None, (str, bool)),
        'album-activated': (GObject.SIGNAL_RUN_FIRST, None, (str, bool)),
        'search': (GObject.SIGNAL_RUN_FIRST, None, (str, str, str)),
        'library-switch-toggled': (GObject.SIGNAL_RUN_FIRST, None, (str, bool)),
    }

    def __init__(self):
        GObject.GObject.__init__(self)
        self.player_track = None
        self.setup_ui()

    def setup_ui(self):
        css = Gtk.CssProvider()
        with open('data/styles.css', 'rb') as f:
            css.load_from_data(f.read())
        try:
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except TypeError:
            pass

        self.builder = Gtk.Builder()
        self.builder.add_from_file("data/mainwindow.ui")
        self.builder.connect_signals(self)

        win = self.builder.get_object("window1")

        # iconview
        iconview = self.builder.get_object("iconview_albums")
        iconview.set_pixbuf_column(1)
        iconview.set_markup_column(2)
        self.builder.get_object('liststore_albums')\
            .set_sort_column_id(3, Gtk.SortType.ASCENDING)
        self.builder.get_object("liststore_playlists")\
            .set_sort_column_id(1, Gtk.SortType.ASCENDING)

        # cellrendereres
        renderers = ['cellrenderertext_playlists', 'cellrenderertext_artists']
        for name in renderers:
            renderer = self.builder.get_object(name)
            renderer.set_property('xpad', 15)
            renderer.set_property('ypad', 15)

        # scale
        scale = self.builder.get_object('scale_player')
        scale.set_range(0, 0)
        self.scale_click_event = False
        self.scale_seek_position = None

        # search
        self.popover_search = Gtk.Popover()
        self.popover_search.set_position(Gtk.PositionType.BOTTOM)
        self.popover_search.set_relative_to(
            self.builder.get_object('button_search_options'))
        self.popover_search.add(self.builder.get_object('box_search_options'))

        # playlist control
        self.popover_playlist_control = Gtk.Popover()
        self.popover_playlist_control.set_position(Gtk.PositionType.TOP)
        self.popover_playlist_control.set_relative_to(
            self.builder.get_object('button_controls_playlist'))
        self.popover_playlist_control.add(
            self.builder.get_object('box_playlist_controls'))
        self.builder.get_object('radiobutton_playlist_alloff').set_active(True)

        # headerbar
        headerbar = CongaHeaderBar(win)
        headerbar.connect('button-clicked', self.on_headerbar_button_clicked)
        headerbar.connect('search-clicked', self.on_headerbar_search_clicked)

        # Showing stuff
        win.show_all()
        self.builder.get_object('box_player_controls').hide()
        self.builder.get_object('notebook1').hide()

    def generate_artist_albumbox(self, tracks, liststore, get_visible_cb, get_switch_cb):
        album = tracks[0].album
        ui = Gtk.Builder()
        ui.add_from_file("data/albumbox.ui")
        album_box = ui.get_object('box_album')
        ui.get_object('label_album_name').set_text(album.name)

        image = ui.get_object('image_album')
        pixbuf = album.get_pixbuf(updater=self.get_image_updater(image))\
            .scale_simple(120, 120, GdkPixbuf.InterpType.BILINEAR)
        image.set_from_pixbuf(pixbuf)

        switch = ui.get_object('switch_library')
        switch.set_state(all([track.in_library for track in tracks]))
        switch.connect('state-set', get_switch_cb(album.uri))

        list_filter = liststore.filter_new()
        list_filter.set_visible_func(get_visible_cb(album.uri))

        treeview = ui.get_object('treeview_tracks')
        treeview.set_model(list_filter)
        treeview.connect('row-activated', self.on_tracklist_row_activated)

        winctx = self.builder.get_object('window1').get_style_context()
        bgcolor = winctx.get_background_color(Gtk.StateFlags.NORMAL)
        color = winctx.get_color(Gtk.StateFlags.NORMAL)
        treeview.override_background_color(Gtk.StateFlags.NORMAL, bgcolor)
        treeview.override_color(Gtk.StateFlags.NORMAL, color)

        return album_box

    def get_playlist_next(self, track_uri, n=1):
        control = [x.get_name() for x in
                   self.builder.get_object(
                       'radiobutton_playlist_shuffle').get_group()
                   if x.get_active()][0]

        model = self.builder.get_object('liststore_tracklist')
        playlist = [model.get_value(row.iter, 0) for row in model]

        if track_uri not in playlist:
            self.update_player_state_stopped()
            return

        i = playlist.index(track_uri)
        if control == 'repeat1':
            i = i
        elif control == 'repeatall' and i >= len(playlist) - 1:
            i -= len(playlist) - 1 + n - 1
        elif control == 'repeatall' and i <= 0:
            i = len(playlist) - i + n
        elif control == 'shuffle':
            i = random.randint(0, len(playlist) - 1)
        else:
            i += n

        if control == 'alloff' and (i > len(playlist) or i < 0):
            i = None

        if i is not None and track_uri in playlist:
            next_uri = playlist[i]
            return next_uri
        else:
            self.update_player_state_stopped()

    def get_image_updater(self, image):
        def updater(pixbuf):
            image.set_from_pixbuf(pixbuf.scale_simple(
                120, 120, GdkPixbuf.InterpType.BILINEAR))
        return updater

    def on_radiobutton_playlist_clicked(self, button):
        control = [x.get_name() for x in
                   self.builder.get_object(
                       'radiobutton_playlist_shuffle').get_group()
                   if x.get_active()][0]
        icons = {'repeatall': 'media-playlist-repeat', 'repeat1': 'media-playlist-repeat',
                 'shuffle': 'media-playlist-shuffle'}
        icon_name = icons.get(control, 'go-next')
        self.builder.get_object('image_playlist_control')\
            .set_from_icon_name(icon_name, Gtk.IconSize.BUTTON)

    def on_headerbar_button_clicked(self, headerbar, tab):
        self.builder.get_object('notebook1').set_current_page(tab)

    def on_headerbar_search_clicked(self, headerbar):
        self.builder.get_object('revealer_search').set_reveal_child(True)
        self.builder.get_object('searchentry1').grab_focus()

    def on_notebook1_switch_page(self, notebook, widget, page):
        self.reset_search()
        self.emit('tab-changed', page, None)

    def on_iconviewAlbums_item_activated(self, view, path):
        model = view.get_model()
        album_uri = model.get_value(model.get_iter(path), 0)
        self.builder.get_object(
            'notebook1').set_current_page(TAB_ALBUM_DETAILS)
        self.emit('album-activated', album_uri, False)

    def on_scale_player_button_press_event(self, scale, event):
        self.scale_click_event = True

    def on_scale_player_value_changed(self, scale):
        if self.scale_click_event:
            self.emit('player-seek', scale.get_value())

    def on_scale_player_button_release_event(self, scale, event):
        self.scale_click_event = False

    def on_button_play_clicked(self, *args):
        self.emit('player-pause')

    def on_button_next_clicked(self, *args):
        self.emit('player-next')

    def on_button_previous_clicked(self, *args):
        self.emit('player-previous')

    def on_window1_realize(self, *args):
        winctx = self.builder.get_object('window1').get_style_context()
        bgcolor = winctx.get_background_color(Gtk.StateFlags.NORMAL)
        color = winctx.get_color(Gtk.StateFlags.NORMAL)

        views = ['treeview_album_details_tracks', 'treeview_playlist_tracks',
                 'treeview_search_albums', 'treeview_search_artists', 'treeview_search_tracks']
        for view in views:
            view = self.builder.get_object(view)
            view.override_background_color(Gtk.StateFlags.NORMAL, bgcolor)
            view.override_color(Gtk.StateFlags.NORMAL, color)

    def on_treeview_playlists_row_activated(self, _view,
                                            path, _column):
        model = self.builder.get_object('liststore_playlists')
        miter = model.get_iter(path)
        uri = model.get_value(miter, 0)
        self.emit('playlist-activated', uri)

    def on_treeview_artists_row_activated(self, view, path, _column):
        model = view.get_model()
        uri = model.get_value(model.get_iter(path), 0)
        self.emit('artist-activated', uri, False)

    def on_tracklist_row_activated(self, view, path, _column):
        model = view.get_model()
        track_uri = model.get_value(model.get_iter(path), 0)
        self.emit('player-play', track_uri)

    def on_searchentry1_search_changed(self, seachentry):

        def emit_search_signal(keywords):
            if self.builder.get_object('searchentry1').get_text() != keywords:
                return

            sources = [x.get_name() for x in
                       self.builder.get_object(
                           'radiobutton_search_sources_all').get_group()
                       if x.get_active()][0]
            match = [x.get_name() for x in
                     self.builder.get_object(
                         'radiobutton_search_match_all').get_group()
                     if x.get_active()][0]

            self.emit('search', keywords, sources, match)

        keywords = seachentry.get_text()
        if len(keywords) > 3:
            GObject.timeout_add(2000, emit_search_signal, keywords)

    def on_togglebutton_search_options_clicked(self, button):
        self.popover_search.show_all()

    def on_treeview_search_artists_row_activated(self, view, path, _column):
        model = view.get_model()
        uri = model.get_value(model.get_iter(path), 0)
        self.emit('artist-activated', uri, True)

    def on_treeview_search_albums_row_activated(self, view, path, _column):
        model = view.get_model()
        uri = model.get_value(model.get_iter(path), 0)
        self.emit('album-activated', uri, True)

    def on_button_controls_playlist_clicked(self, button):
        self.popover_playlist_control.show()

    def reset_search(self):
        self.builder.get_object('revealer_search').set_reveal_child(False)
        self.update_search_results({})

    def update_tabs(self, tracks):
        if tracks:
            self.builder.get_object('box_loading_tracks').hide()
            self.builder.get_object('notebook1').show()

    def update_tab_albums(self, albums):
        liststore = self.builder.get_object("liststore_albums")
        liststore.clear()
        liststore_idx = [liststore.get_value(row.iter, 2) for row in liststore]

        def get_updater(uri):
            def updater(pixbuf):
                self.update_pixbuf_liststore(
                    pixbuf, 'liststore_albums', uri, 125)
            return updater

        for album in albums:
            if not album.name or album.uri in liststore_idx or album.num_tracks < 4:
                continue

            pixbuf = album.get_pixbuf(updater=get_updater(album.uri))
            pixbuf = pixbuf.scale_simple(
                125, 125, GdkPixbuf.InterpType.BILINEAR)
            label = "<span size=\"medium\">{album}</span>\n"\
                    "<span size=\"small\">{artist}</span>".format(
                        album=utils.add_ellipse(cgi.escape(
                            album.name.replace('& ', ''))),
                        artist=utils.add_ellipse(cgi.escape(album.artist.name.replace('& ', ''))))
            liststore.append([album.uri, pixbuf, label, album.artist.name])

    def update_tab_artists(self, artists):
        liststore = self.builder.get_object("liststore_playlists")
        liststore.clear()
        liststore_idx = [liststore.get_value(row.iter, 0) for row in liststore]

        for artist in artists:
            name = cgi.escape(artist.name)
            if name in liststore_idx:
                continue
            liststore.append([artist.uri, name])

        view = self.builder.get_object('treeview_artists')
        selection = view.get_selection()
        model, iter = selection.get_selected()
        if iter:
            path = iter.get_selected_rows()[0]
        else:
            path = model[0].path
        self.on_treeview_artists_row_activated(view, path, None)

    def update_tab_playlists(self, playlists):
        liststore = self.builder.get_object("liststore_playlists")
        liststore.clear()
        liststore_idx = [liststore.get_value(row.iter, 0) for row in liststore]

        for uri, playlist in playlists.items():
            name = cgi.escape(playlist.name)
            if name in liststore_idx:
                continue
            liststore.append([uri, name])

        view = self.builder.get_object('treeview_playlists')
        selection = view.get_selection()
        model, iter = selection.get_selected()
        if iter:
            path = iter.get_selected_rows()[0]
        else:
            path = model[0].path
        self.on_treeview_playlists_row_activated(view, path, None)

    def update_tab_album_details(self, album, tracks):
        pixbuf = album.get_pixbuf().scale_simple(
            250, 250, GdkPixbuf.InterpType.BILINEAR)
        self.builder.get_object('image_album_details').set_from_pixbuf(pixbuf)
        self.builder.get_object(
            'label_album_details_album').set_text(album.name)
        self.builder.get_object(
            'label_album_details_artist').set_text(album.artist.name)
        self.builder.get_object('label_album_details_length').set_text(
            '%s min' % int(sum([x.length for x in tracks]) / 60000))
        self.builder.get_object('label_album_details_released').set_text(
            str(album.date.year) if album.date else '----')

        self.update_tracklist(tracks)

    def update_tab_artist_details(self, artist, tracks, page=TAB_ARTISTS):
        if page == TAB_ARTISTS:
            label_artist_name = self.builder.get_object('label_artist_name')
            box = self.builder.get_object('box_artist_albums')
        elif page == TAB_ARTIST_DETAILS:
            label_artist_name = self.builder.get_object('label_artist_details_name')
            box = self.builder.get_object('box_artist_details_albums')

        label_artist_name.set_text(artist.name)

        for child in box.get_children():
            child.destroy()

        liststore = self.builder.get_object('liststore_tracklist')
        liststore.clear()

        def get_visible_cb(album_uri):
            def is_visible(model, iter, data):
                track_uri = model.get_value(iter, 0)
                track = [track for track in tracks if track.uri == track_uri][0]
                return track.album.uri == album_uri
            return is_visible

        def get_switch_cb(album_uri):
            def on_switch_activate(switch, state):
                self.emit('library-switch-toggled', album_uri, state)
            return on_switch_activate

        albums = defaultdict(list)
        for track in tracks:
            albums[track.album.uri].append(track)

        for _, atracks in sorted(albums.items(), key=lambda x: x[1][0].album.date):
            album_box = self.generate_artist_albumbox(
                atracks, liststore, get_visible_cb, get_switch_cb)
            box.pack_start(album_box, True, True, 10)

        self.update_tracklist(tracks)

    def update_player_state_playing(self, track):
        scale = self.builder.get_object('scale_player')
        scale.set_range(0, track.length)

        play_image = self.builder.get_object('image_button_player')
        play_image.set_from_stock('gtk-media-pause', Gtk.IconSize.BUTTON)
        self.builder.get_object('label_controls_duration').set_text(
            '0:00 / %s' % utils.format_time(track.length))

        self.builder.get_object('box_player_controls').show()
        self.builder.get_object('label_controls_track').set_text(track.name)
        self.builder.get_object('label_controls_artist').set_text(
            track.album.artist.name)

        def get_updater(image):
            def updater(pixbuf):
                image.set_from_pixbuf(pixbuf.scale_simple(
                    30, 30, GdkPixbuf.InterpType.BILINEAR))
            return updater

        image = self.builder.get_object('image_controls_album_image')
        pixbuf = track.album.get_pixbuf(updater=get_updater(image))\
            .scale_simple(30, 30, GdkPixbuf.InterpType.BILINEAR)
        image.set_from_pixbuf(pixbuf)

        self.player_track = track.uri

        self.update_tracklist_playing()

    def update_player_state_stopped(self):
        scale = self.builder.get_object('scale_player')
        scale.set_value(0)
        scale.set_range(0, 0)

        play_image = self.builder.get_object('image_button_player')
        play_image.set_from_stock('gtk-media-play', Gtk.IconSize.BUTTON)
        self.builder.get_object('box_player_controls').hide()
        self.update_tracklist_playing()

    def update_box_search_options_sources(self, options):
        box = self.builder.get_object('box_search_options_sources')
        for plugin in options:
            radiobutton = Gtk.RadioButton(plugin.capitalize())
            radiobutton.join_group(self.builder.get_object(
                'radiobutton_search_sources_all'))
            radiobutton.set_name(plugin)
            box.add(radiobutton)

    def update_search_results(self, results):
        if results:
            self.builder.get_object('notebook1').set_current_page(TAB_SEARCH)
        liststore_albums = self.builder.get_object('liststore_search_albums')
        liststore_albums.clear()

        def get_updater(uri):
            def updater(pixbuf):
                self.update_pixbuf_liststore(
                    pixbuf, 'liststore_search_albums', uri, 50)
            return updater

        for uri, album in results.get('albums', {}).items():
            pixbuf = album.get_pixbuf(updater=get_updater(uri))\
                .scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
            label = "<span size=\"medium\">{album}</span>\n"\
                    "<span size=\"small\">{artist}</span>".format(
                        album=utils.add_ellipse(cgi.escape(album.name.replace('& ', ''))),
                        artist=utils.add_ellipse(cgi.escape(album.artist.name.replace('& ', ''))))
            liststore_albums.append([album.uri, pixbuf, label])

        liststore_artists = self.builder.get_object('liststore_search_artists')
        liststore_artists.clear()

        def get_updater(uri):
            def updater(pixbuf):
                self.update_pixbuf_liststore(
                    pixbuf, 'liststore_search_artists', uri, 50)
            return updater

        for uri, artist in results.get('artists', {}).items():
            pixbuf = artist.get_pixbuf(updater=get_updater(uri))\
                .scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
            label = "<span size=\"medium\">{artist}</span>"\
                    .format(artist=utils.add_ellipse(cgi.escape(artist.name.replace('& ', ''))))
            liststore_artists.append([artist.uri, pixbuf, label])

        self.update_tracklist(
            [track for uri, track in results.get('tracks', {}).items()])

    def update_playlist_details(self, playlist):
        tracks = playlist.tracks
        self.update_tracklist(tracks)

        self.builder.get_object('label_playlist_name').set_text(playlist.name)
        self.builder.get_object('label_playlist_num_songs').set_text(
            ('%s Song' if len(tracks) == 0 else '%s Songs') % len(tracks))

    def update_tracklist(self, tracks):
        liststore = self.builder.get_object("liststore_tracklist")
        liststore.clear()

        for track in tracks:
            liststore.append(
                [track.uri, '',
                 utils.add_ellipse(
                     track.name, 40), utils.format_time(track.length),
                 utils.add_ellipse(track.album.artist.name, 40),
                 utils.add_ellipse(track.album.name, 40), None])
        self.update_tracklist_playing()

    def update_tracklist_playing(self):
        model = self.builder.get_object('liststore_tracklist')

        for row in model:
            if model.get_value(row.iter, 0) == self.player_track:
                model.set_value(row.iter, 1, 'gtk-media-play')
                model.set_value(row.iter, 6, 400)
            else:
                model.set_value(row.iter, 1, None)
                model.set_value(row.iter, 6, None)

    def update_scale(self, pos):
        scale = self.builder.get_object('scale_player')
        if scale.get_adjustment().get_upper() <= 0 or self.scale_click_event:
            return

        scale.set_value(pos)

        duration_label = self.builder.get_object('label_controls_duration')
        splitted_label = duration_label.get_text().split(' / ')
        duration = sum([utils.convert_to_mseconds(x)
                        for x in splitted_label]) + 1000
        duration_label.set_text(
            '%s / %s' % (utils.format_time(int(pos)), utils.format_time(duration - pos)))
        return True

    def update_pixbuf_liststore(self, pixbuf, liststore_name, uri, size):
        liststore = self.builder.get_object(liststore_name)
        liststore_idx = [liststore.get_value(row.iter, 0) for row in liststore]
        pixbuf = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        row = liststore[liststore_idx.index(uri)]
        liststore.set_value(row.iter, 1, pixbuf)
