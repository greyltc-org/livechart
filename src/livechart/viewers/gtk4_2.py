# main.py
#
# Copyright 2022 Grey Christoforo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import gi

gi.require_version('Gtk', '4.0')

from gi.repository import Gtk, Gio

window_ui ="""
<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <requires lib="gtk" version="4.0"/>
  <template class="LivechartWindow" parent="GtkApplicationWindow">
    <property name="default-width">600</property>
    <property name="default-height">300</property>
    <child type="titlebar">
      <object class="GtkHeaderBar" id="header_bar">
        <child type="end">
          <object class="GtkMenuButton">
            <property name="icon-name">open-menu-symbolic</property>
            <property name="menu-model">primary_menu</property>
          </object>
        </child>
        <child type="start">
          <object class="GtkButton" id="st_btn">
            <property name="label">Start</property>
          </object>
        </child>
        <child type="start">
          <object class="GtkButton" id="stp_btn">
            <property name="label">Stop</property>
          </object>
        </child>
      </object>
    </child>
    <child>
      <object class="GtkBox">
        <property name="orientation">GTK_ORIENTATION_VERTICAL</property>
        <child>
          <object class="GtkLabel" id="label">
            <property name="label">Hello, World!</property>
            <property name="vexpand">True</property>
            <property name="vexpand-set">True</property>
            <attributes>
              <attribute name="weight" value="bold"/>
              <attribute name="scale" value="2"/>
            </attributes>
          </object>
        </child>
        <child>
          <object class="GtkBox">
            <child>
              <object class="GtkLabel" id="label3">
                <property name="label">Hello, World3!</property>
                <property name="hexpand">True</property>
                <property name="hexpand-set">True</property>
              </object>
            </child>
            <child>
              <object class="GtkEntry" id="number">
                <property name="placeholder-text">Latest Value</property>
                <property name="max-length">12</property>
                <property name="truncate-multiline">True</property>
                <property name="editable">False</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
  </template>

  <menu id="primary_menu">
    <section>
      <item>
        <attribute name="label" translatable="yes">_Preferences</attribute>
        <attribute name="action">app.preferences</attribute>
      </item>
      <item>
        <attribute name="label" translatable="yes">_Keyboard Shortcuts</attribute>
        <attribute name="action">win.show-help-overlay</attribute>
      </item>
      <item>
        <attribute name="label" translatable="yes">_About lc3</attribute>
        <attribute name="action">app.about</attribute>
      </item>
    </section>
  </menu>
</interface>
"""

help_overlay_ui="""
<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <template class="LivechartHol" parent="GtkShortcutsWindow">
    <property name="modal">True</property>
    <child>
      <object class="GtkShortcutsSection">
        <property name="section-name">shortcuts</property>
        <property name="max-height">10</property>
        <child>
          <object class="GtkShortcutsGroup">
            <property name="title" translatable="yes" context="shortcut window">General</property>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes" context="shortcut window">Show Shortcuts</property>
                <property name="action-name">win.show-help-overlay</property>
              </object>
            </child>
            <child>
              <object class="GtkShortcutsShortcut">
                <property name="title" translatable="yes" context="shortcut window">Quit</property>
                <property name="action-name">app.quit</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
  </template>
</interface>
"""


@Gtk.Template(string=window_ui)
class LivechartWindow(Gtk.ApplicationWindow):
    __gtype_name__ = 'LivechartWindow'

    #label = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@Gtk.Template(string=help_overlay_ui)
class LivechartHol(Gtk.ShortcutsWindow):
    __gtype_name__ = 'LivechartHol'

    #label = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class AboutDialog(Gtk.AboutDialog):

    def __init__(self, parent):
        Gtk.AboutDialog.__init__(self)
        self.props.program_name = 'livechart'
        self.props.version = "0.1.0"
        self.props.authors = ['Grey Christoforo']
        self.props.copyright = '(C) 2022 Grey Christoforo'
        self.props.logo_icon_name = 'org.greyltc.livechart'
        self.set_transient_for(parent)


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.greyltc.livechart',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = LivechartWindow(application=self)
        
        win.set_help_overlay(LivechartHol())
        self.set_accels_for_action('win.show-help-overlay',['<Control>question'])

        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        win.present()

    def on_about_action(self, widget, _):
        about = AboutDialog(self.props.active_window)
        about.present()

    def on_preferences_action(self, widget, _):
        print('app.preferences action activated')

    def create_action(self, name, callback):
        """ Add an Action and connect to a callback """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)


def main():
    app = Application()
    return app.run(sys.argv)

if __name__ == "__main__":
    main()
