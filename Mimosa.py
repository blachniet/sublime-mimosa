import os
import subprocess
import sublime
import sublime_plugin
import time
import functools
import threading

def open_url(url):
  sublime.active_window().run_command('open_url', {"url": url})

def main_thread(callback, *args, **kwargs):
  # sublime.set_timeout gets used to send things onto the main thread
  # most sublime.[something] calls need to be on the main thread
  sublime.set_timeout(functools.partial(callback, *args, **kwargs), 0)

def _make_text_safeish(text, fallback_encoding):
  # The unicode decode here is because sublime converts to unicode inside
  # insert in such a way that unknown characters will cause errors, which is
  # distinctly non-ideal... and there's no way to tell what's coming out of
  # git in output. So...
  try:
    unitext = text.decode('utf-8')
  except UnicodeDecodeError:
    unitext = text.decode(fallback_encoding)
  return unitext

class MimosaCommandThread(threading.Thread):
  def __init__(self, command, on_done, on_progress, working_dir="", fallback_encoding=""):
    threading.Thread.__init__(self)
    self.command = command
    self.on_done = on_done
    self.on_progress = on_progress
    self.working_dir = working_dir
    self.fallback_encoding = fallback_encoding

  def run(self):
    try:
      # Per http://bugs.python.org/issue8557 shell=True is required to
      # get $PATH on Windows. Yay portable code.
      shell = os.name == 'nt'
      if self.working_dir != "":
        os.chdir(self.working_dir)
      proc = subprocess.Popen(self.command,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        shell=shell, universal_newlines=True)

      if self.on_progress != None:
        while proc.poll() is None:
          line = proc.stdout.readline()
          main_thread(self.on_progress, _make_text_safeish(line, self.fallback_encoding))
        main_thread(self.on_done, '')
      else:
        output = proc.communicate()[0]
        main_thread(self.on_done, _make_text_safeish(output, self.fallback_encoding))
      # if sublime's python gets bumped to 2.7 we can just do:
      # output = subprocess.check_output(self.command)
      # main_thread(self.on_done, _make_text_safeish(output, self.fallback_encoding))
    except subprocess.CalledProcessError, e:
      main_thread(self.on_done, e.returncode)
    except OSError, e:
      if e.errno == 2:
        main_thread(sublime.error_message, "Node binary could not be found in PATH\n\nConsider using the node_command setting for the Node plugin\n\nPATH is: %s" % os.environ['PATH'])
      else:
        raise e

class MimosaCommand(sublime_plugin.TextCommand):
    def run_command(self, command, callback=None, progress_callback=None, show_status=True, filter_empty_args=True, **kwargs):

        if 'working_dir' not in kwargs:
            kwargs['working_dir'] = self.get_working_dir()
        if not callback:
            callback = self.generic_done

        thread = MimosaCommandThread(command, callback, progress_callback, **kwargs)
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

    def kill_node(self):
        sublime.status_message('Killing node...')
        if os.name == 'nt':     # Kill Node on Windows
            command = """taskkill /f /im node.exe"""
        else:                   # Kill Node on Unix
            command = """kill -9 `ps -ef | grep node | grep -v grep | awk '{print $2}'`"""
        os.system(command)

    def get_node_cmd(self, command):
        if os.name == 'nt':     # Windows commands are *.cmd files
            return command + '.cmd'
        return command

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

class MimosaWatch(MimosaTextCommand):
    def run(self, edit):
        self.kill_node()
        self.proc_watch = subprocess.Popen(self.get_node_cmd('mimosa') + ' watch')

class MimosaWatchS(MimosaTextCommand):

    # def _output_to_view(self, output_file, output, clear=False, syntax="Packages/JavaScript/JavaScript.tmLanguage"):
    #     output_file.set_syntax_file(syntax)
    #     edit = output_file.begin_edit()
    #     if clear:
    #         region = sublime.Region(0, self.output_view.size())
    #         output_file.erase(edit, region)
    #     output_file.insert(edit, 0, output)
    #     output_file.end_edit(edit)

    def on_progress(self, out):
        self.watch_output_view.set_read_only(False)

        edit = self.watch_output_view.begin_edit()
        self.watch_output_view.insert(edit, self.watch_output_view.size(), out.replace('[32m[1m',''))
        self.watch_output_view.end_edit(edit)
        
        self.watch_output_view.set_read_only(True)

    def run(self, edit):
        self.kill_node()
        self.watch_output_view = self.get_window().new_file()
        self.watch_output_view.set_name("Mimosa Output")
        self.watch_output_view.set_scratch(True)
        self.run_command(['mimosa', 'watch', '-s'], progress_callback=self.on_progress)

class MimosaBuildOm(MimosaTextCommand):
    def run(self, edit):
        self.run_command(['mimosa', 'build', '-om'])

class MimosaBuildOmp(MimosaTextCommand):
    def run(self, edit):
        self.run_command(['mimosa', 'build', '-omp'])

class MimosaClean(MimosaTextCommand):
    def on_progress(self, out):
        print "==> " + out.rstrip('\n')

    def run(self, edit):
        self.kill_node()
        self.run_command(['mimosa', 'clean'], progress_callback=self.on_progress)

class MimosaCleanF(MimosaTextCommand):
    def run(self, edit):
        self.kill_node()
        self.run_command(['mimosa', 'clean', '-f'])

