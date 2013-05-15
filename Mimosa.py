import os
import subprocess
import sublime
import sublime_plugin
import time

from lib.command_thread import CommandThread

def open_url(url):
  sublime.active_window().run_command('open_url', {"url": url})

class MimosaCommand(sublime_plugin.TextCommand):
    def run_command(self, command, callback=None, show_status=True, filter_empty_args=True, **kwargs):

        if 'working_dir' not in kwargs:
            kwargs['working_dir'] = self.get_working_dir()
        if not callback:
            callback = self.generic_done

        thread = CommandThread(command, callback, **kwargs)
        thread.start()

        if show_status:
            message = kwargs.get('status_message', False) or ' '.join(command)
            sublime.status_message(message)

    def generic_done(self, result):
        if not result.strip():
            return
        self.panel(result)

    def _output_to_view(self, output_file, output, clear=False, syntax="Packages/JavaScript/JavaScript.tmLanguage"):
        output_file.set_syntax_file(syntax)
        edit = output_file.begin_edit()
        if clear:
            region = sublime.Region(0, self.output_view.size())
            output_file.erase(edit, region)
        output_file.insert(edit, 0, output)
        output_file.end_edit(edit)

    def scratch(self, output, title=False, **kwargs):
        scratch_file = self.get_window().new_file()
        if title:
            scratch_file.set_name(title)
        scratch_file.set_scratch(True)
        self._output_to_view(scratch_file, output, **kwargs)
        scratch_file.set_read_only(True)
        return scratch_file

    def panel(self, output, **kwargs):
        if not hasattr(self, 'output_view'):
            self.output_view = self.get_window().get_output_panel("mimosa")
        self.output_view.set_read_only(False)
        self._output_to_view(self.output_view, output, clear=True, **kwargs)
        self.output_view.set_read_only(True)
        self.get_window().run_command("show_panel", {"panel": "output.mimosa"})

    def quick_panel(self, *args, **kwargs):
        self.get_window().show_quick_panel(*args, **kwargs)

    def stop_node_now(self):
        command = """taskkill /F /IM node.exe"""
        os.system(command)

class MimosaTextCommand(MimosaCommand, sublime_plugin.TextCommand):
  def active_view(self):
    return self.view

  def is_enabled(self):
    # First, is this actually a file on the file system?
    if self.view.file_name() and len(self.view.file_name()) > 0:
      return os.path.realpath(self.get_working_dir())

  def get_file_name(self):
    return os.path.basename(self.view.file_name())

  def get_working_dir(self):
    return os.path.dirname(self.view.file_name())

  def get_window(self):
    # Fun discovery: if you switch tabs while a command is working,
    # self.view.window() is None. (Admittedly this is a consequence
    # of my deciding to do async command processing... but, hey,
    # got to live with that now.)
    # I did try tracking the window used at the start of the command
    # and using it instead of view.window() later, but that results
    # panels on a non-visible window, which is especially useless in
    # the case of the quick panel.
    # So, this is not necessarily ideal, but it does work.
    return self.view.window() or sublime.active_window()

class MimosaWatchAndServe(MimosaTextCommand):
    def run(self, edit):
        self.stop_node_now()
        self.proc_watch = subprocess.Popen('mimosa.cmd watch -s')

class MimosaClean(MimosaTextCommand):
    def run(self, edit):
        self.stop_node_now()
        self.proc_clean = subprocess.Popen('mimosa.cmd clean')

class MimosaKillNode(MimosaTextCommand):
    def run(self, edit):
        command = ['taskkill', '/f', '/im', 'node.exe']
        self.run_command(command)

