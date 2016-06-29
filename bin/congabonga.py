import sys
import os.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

from conga.app import CongaApp

if __name__ == "__main__":
    GObject.threads_init()
    app = CongaApp()
    Gtk.main()
