import os
import re
import collections
import json
from .pathlib import Path, PurePosixPath
from .projman_dlg import *

from cudatext import *
import cudatext_cmd

PROJECT_EXTENSION = ".cuda-proj"
PROJECT_DIALOG_FILTER = "CudaText projects|*"+PROJECT_EXTENSION
PROJECT_UNSAVED_NAME = "(Unsaved project)"
NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD = range(4)
global_project_info = {}

def project_variables():
    """
    gives dict with "project variables", which is ok for using from other plugins,
    e.g. ExtTools.
    add to names {} or $() if you want.
    1) predefined var ProjMainFile (defined by right-click menu in ProjMan)
    2) predefined var ProjDir (dir of .cuda-proj file)
    3) other vars are defined by user in Proj Properties dialog.
    """
    res = collections.OrderedDict()
    data = global_project_info
    res['ProjDir'] = os.path.dirname(data.get('filename', ''))

    fn = data.get('mainfile', '')
    res['ProjMainFile'] = fn
    res['ProjMainFileNameOnly'] = os.path.basename(fn)
    res['ProjMainFileNameNoExt'] = '.'.join(os.path.basename(fn).split('.')[0:-1])

    data = global_project_info.get('vars', [])
    for item in data:
        s1, s2 = item.split('=', maxsplit=1)
        res[s1] = s2
    return res

NodeInfo = collections.namedtuple("NodeInfo", "caption image")


def is_filename_mask_listed(name, mask_list):
    #s = os.path.basename(name)
    s = name.lower() #enough for s.endswith
    for item in mask_list.split(' '):
        #if fnmatch(s, item): #slow, lets do it faster
        if s.endswith(item):
            return True
    return False

def is_locked(s):
    return not os.access(s, os.R_OK)


def _toolbar_add_btn(h_bar, hint, icon=-1, command=''):
    toolbar_proc(h_bar, TOOLBAR_ADD_ITEM)
    cnt = toolbar_proc(h_bar, TOOLBAR_GET_COUNT)
    h_btn = toolbar_proc(h_bar, TOOLBAR_GET_BUTTON_HANDLE, index=cnt-1)
    if hint=='-':
        button_proc(h_btn, BTN_SET_KIND, BTNKIND_SEP_HORZ)
    else:
        button_proc(h_btn, BTN_SET_KIND, BTNKIND_ICON_ONLY)
        button_proc(h_btn, BTN_SET_HINT, hint)
        button_proc(h_btn, BTN_SET_IMAGEINDEX, icon)
        button_proc(h_btn, BTN_SET_DATA1, command)


class Command:

    title = "Project"
    menuitems = (
        ("New project"          , "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Open project..."      , "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Recent projects"      , "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Save project as..."   , "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("-"                    , "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Go to file..."        , "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Project properties...", "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Config..."            , "proj", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),

        ("Add folder..."        , "nodes", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Add file..."          , "nodes", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Clear project"        , "nodes", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Remove node"          , "nodes", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),

        ("New file..."          , "dir", [NODE_DIR]),
        ("Rename..."            , "dir", [NODE_DIR]),
        ("Delete directory"     , "dir", [NODE_DIR]),
        ("New directory..."     , "dir", [NODE_DIR]),
        ("Find in directory..." , "dir", [NODE_DIR]),

        ("Rename..."            , "file", [NODE_FILE]),
        ("Delete file"          , "file", [NODE_FILE]),
        ("Set as main file"     , "file", [NODE_FILE]),

        ("-"                    , "", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
        ("Refresh"              , "", [None, NODE_PROJECT, NODE_DIR, NODE_FILE, NODE_BAD]),
    )

    options = {
        "recent_projects": [],
        "masks_ignore": MASKS_IGNORE,
        "on_start": False,
        "toolbar": True,
    }

    tree = None
    h_dlg = None
    h_menu = None

    def __init__(self):
        settings_dir = Path(app_path(APP_DIR_SETTINGS))
        self.options_filename = settings_dir / "cuda_project_man.json"
        if self.options_filename.exists():
            with self.options_filename.open(encoding='utf8') as fin:
                self.options = json.load(fin)

        self.new_project()


    def init_form_main(self):

        show_toolbar = self.options.get("toolbar", True)

        self.h_dlg = dlg_proc(0, DLG_CREATE)

        dlg_proc(self.h_dlg, DLG_PROP_SET, {
            'keypreview': True,
            'on_key_down': self.form_key_down,
            } )

        n = dlg_proc(self.h_dlg, DLG_CTL_ADD, prop='toolbar')
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, index=n, prop={
            'name':'bar',
            'a_r':('',']'), #anchor to top: l,r,t
            'vis': show_toolbar,
            } )

        self.h_bar = dlg_proc(self.h_dlg, DLG_CTL_HANDLE, index=n)
        self.toolbar_imglist = toolbar_proc(self.h_bar, TOOLBAR_GET_IMAGELIST)

        dirname = os.path.join(os.path.dirname(__file__), 'icons')
        icon_open = imagelist_proc(self.toolbar_imglist, IMAGELIST_ADD, value = os.path.join(dirname, 'tb-open.png'))
        icon_save = imagelist_proc(self.toolbar_imglist, IMAGELIST_ADD, value = os.path.join(dirname, 'tb-save.png'))
        icon_add_file = imagelist_proc(self.toolbar_imglist, IMAGELIST_ADD, value = os.path.join(dirname, 'tb-add-file.png'))
        icon_add_dir = imagelist_proc(self.toolbar_imglist, IMAGELIST_ADD, value = os.path.join(dirname, 'tb-add-dir.png'))
        icon_del = imagelist_proc(self.toolbar_imglist, IMAGELIST_ADD, value = os.path.join(dirname, 'tb-del.png'))
        icon_cfg = imagelist_proc(self.toolbar_imglist, IMAGELIST_ADD, value = os.path.join(dirname, 'tb-cfg.png'))

        toolbar_proc(self.h_bar, TOOLBAR_THEME)
        _toolbar_add_btn(self.h_bar, hint='Open project', icon=icon_open, command='cuda_project_man.action_open_project' )
        _toolbar_add_btn(self.h_bar, hint='Save project as', icon=icon_save, command='cuda_project_man.action_save_project_as' )
        _toolbar_add_btn(self.h_bar, hint='-' )
        _toolbar_add_btn(self.h_bar, hint='Add folder', icon=icon_add_dir, command='cuda_project_man.action_add_folder' )
        _toolbar_add_btn(self.h_bar, hint='Add file', icon=icon_add_file, command='cuda_project_man.action_add_file' )
        _toolbar_add_btn(self.h_bar, hint='Remove node', icon=icon_del, command='cuda_project_man.action_remove_node' )
        _toolbar_add_btn(self.h_bar, hint='-' )
        _toolbar_add_btn(self.h_bar, hint='Config', icon=icon_cfg, command='cuda_project_man.action_config' )

        n = dlg_proc(self.h_dlg, DLG_CTL_ADD, prop='treeview')
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, index=n, prop={
            'name':'tree',
            'a_t':('bar', ']'),
            'a_r':('',']'), #anchor to entire form
            'a_b':('',']'),
            'on_menu': 'cuda_project_man.tree_on_menu',
            'on_unfold': 'cuda_project_man.tree_on_unfold',
            'on_click': 'cuda_project_man.tree_on_click',
            #'on_click_dbl': 'cuda_project_man.tree_on_click_dbl',
            } )

        self.tree = dlg_proc(self.h_dlg, DLG_CTL_HANDLE, index=n)
        self.tree_imglist = tree_proc(self.tree, TREE_GET_IMAGELIST)
        tree_proc(self.tree, TREE_PROP_SHOW_ROOT, text='0')
        tree_proc(self.tree, TREE_ITEM_DELETE, 0)

        self.icon_init()
        self.ICON_ALL = self.icon_get('_')
        self.ICON_DIR = self.icon_get('_dir')
        self.ICON_PROJ = self.icon_get('_proj')
        self.ICON_BAD = self.icon_get('_bad')
        self.ICON_ZIP = self.icon_get('_zip')
        self.ICON_BIN = self.icon_get('_bin')
        self.ICON_IMG = self.icon_get('_img')


    def init_panel(self, and_activate=True):
        # already inited?
        if self.tree:
            return

        self.init_form_main()

        dlg_proc(self.h_dlg, DLG_SCALE)
        tree_proc(self.tree, TREE_THEME) #TREE_THEME only after DLG_SCALE

        app_proc(PROC_SIDEPANEL_ADD_DIALOG, (self.title, self.h_dlg, 'project.png'))

        if and_activate:
            self.do_show(True)

        self.action_refresh()
        self.generate_context_menu()


    def show_panel(self):
        self.do_show(False)

    def focus_panel(self):
        self.do_show(True)

    def do_show(self, and_focus):
        if not self.tree:
            self.init_panel(True)
        else:
            ed.cmd(cudatext_cmd.cmd_ShowSidePanelAsIs)
            app_proc(PROC_SIDEPANEL_ACTIVATE, self.title)

    @property
    def selected(self):
        return tree_proc(self.tree, TREE_ITEM_GET_SELECTED)

    def add_context_menu_node(self, parent, action, name):
        return menu_proc(parent, MENU_ADD, command=action, caption=name)


    def generate_context_menu(self):
        node_type = None
        if self.selected is not None:
            n = self.get_info(self.selected).image
            if n == self.ICON_PROJ: node_type = NODE_PROJECT
            elif n == self.ICON_DIR: node_type = NODE_DIR
            elif n == self.ICON_BAD: node_type = NODE_BAD
            else: node_type = NODE_FILE

        if not self.h_menu:
            self.h_menu = menu_proc(0, MENU_CREATE)

        menu_all = self.h_menu
        menu_proc(menu_all, MENU_CLEAR)
        menu_proj = self.add_context_menu_node(menu_all, "0", "Project file")
        menu_nodes = self.add_context_menu_node(menu_all, "0", "Root nodes")
        if node_type == NODE_FILE:
            menu_file = self.add_context_menu_node(menu_all, "0", "Selected file")
        if node_type == NODE_DIR:
            menu_dir = self.add_context_menu_node(menu_all, "0", "Selected directory")

        for item in self.menuitems:
            item_caption = item[0]
            item_parent = item[1]
            item_types = item[2]
            if node_type not in item_types:
                continue

            if item_parent == "proj":
                menu_use = menu_proj
            elif item_parent == "nodes":
                menu_use = menu_nodes
            elif item_parent == "file":
                menu_use = menu_file
            elif item_parent == "dir":
                menu_use = menu_dir
            else:
                menu_use = menu_all

            if item_caption in ["-", "Recent projects"]:
                action_name = ""
                action = ""
            else:
                action_name = item_caption.lower().replace(" ", "_").rstrip(".")
                action = "cuda_project_man.action_" + action_name

            menu_added = self.add_context_menu_node(menu_use, action, item_caption)
            if item_caption == "Recent projects":
                for path in self.options["recent_projects"]:
                    action = str.format("module=cuda_project_man;cmd=action_open_project;info=r'{}';", path)
                    self.add_context_menu_node(menu_added, action, path)

    @staticmethod
    def node_ordering(node):
        path = Path(node)
        return path.is_file(), path.name

    def add_node(self, dialog):
        path = dialog()
        if path is not None:
            if path in self.project["nodes"]:
                return
            msg_status("Adding to project: " + path, True)
            self.project["nodes"].append(path)
            self.project["nodes"].sort(key=Command.node_ordering)
            self.action_refresh()
            if self.project_file_path:
                self.action_save_project_as(self.project_file_path)

    def new_project(self):
        self.project = dict(nodes=[])
        self.project_file_path = None
        self.update_global_data()

    def add_recent(self, path):
        recent = self.options["recent_projects"]
        if path in recent:
            recent.pop(recent.index(path))

        self.options["recent_projects"] = ([path] + recent)[:10]
        self.generate_context_menu()

    def action_new_file(self):
        location = Path(self.get_location_by_index(self.selected))
        if location.is_file():
            location = location.parent

        result = dlg_input("New file:", "")
        if not result:
            return

        if os.sep in result:
            msg_status("Incorrect file name")
            return

        path = location / result
        path.touch()
        self.action_refresh()

        #open new file
        self.jump_to_filename(str(path))
        file_open(str(path))

    def action_rename(self):
        location = Path(self.get_location_by_index(self.selected))
        result = dlg_input("Rename to", str(location.name))
        if not result:
            return

        new_location = location.parent / result
        if location == new_location:
            return

        location.replace(new_location)
        if location in self.top_nodes.values():
            self.action_remove_node()
            self.add_node(lambda: str(new_location))

        self.action_refresh()
        self.jump_to_filename(str(new_location))
        msg_status("Renamed to: " + str(new_location.name))

    def action_delete_file(self):
        location = Path(self.get_location_by_index(self.selected))
        if msg_box("Delete file from disk:\n" + str(location), MB_OKCANCEL + MB_ICONWARNING) != ID_OK:
            return

        location.unlink()
        if location in self.top_nodes.values():
            self.action_remove_node()
        else:
            self.action_refresh()
            self.jump_to_filename(str(location.parent))
        msg_status("Deleted file: " + str(location.name))

    def do_delete_dir(self, location):
        for path in location.glob("*"):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                self.do_delete_dir(path)
        location.rmdir()

    def action_delete_directory(self):
        location = Path(self.get_location_by_index(self.selected))
        if msg_box("Delete directory from disk:\n" + str(location), MB_OKCANCEL + MB_ICONWARNING) != ID_OK:
            return

        self.do_delete_dir(location)
        if location in self.top_nodes.values():
            self.action_remove_node()
        else:
            self.action_refresh()
            self.jump_to_filename(str(location.parent))
        msg_status("Deleted dir: " + str(location.name))

    def action_new_directory(self):
        location = Path(self.get_location_by_index(self.selected))
        if location.is_file():
            location = location.parent
        result = dlg_input("New directory", "")
        if not result:
            return

        location = location / result
        location.mkdir()
        self.action_refresh()
        self.jump_to_filename(str(location))

    def action_find_in_directory(self):
        try:
            import cuda_find_in_files as fif
        except ImportError:
            msg_box('Plugin "Find in Files" not installed, install it first', MB_OK + MB_ICONERROR)
            return

        location = str(self.get_location_by_index(self.selected))
        msg_status('Called "Find in Files" for "%s"' % location)
        fif.show_dlg(what="", opts={"fold": location})

    def action_refresh(self, parent=None, nodes=None, depth=2):
        unfold = parent is None
        if parent is None:
            tree_proc(self.tree, TREE_ITEM_DELETE, 0)
            if self.project_file_path is None:
                project_name = PROJECT_UNSAVED_NAME
            else:
                project_name = self.project_file_path.stem

            parent = tree_proc(
                self.tree,
                TREE_ITEM_ADD,
                0,
                -1,
                project_name,
                self.ICON_PROJ,
            )

            #select 1st node
            items_root = tree_proc(self.tree, TREE_ITEM_ENUM, 0)
            tree_proc(self.tree, TREE_ITEM_SELECT, items_root[0][0])

            nodes = self.project["nodes"]
            self.top_nodes = {}

        for path in map(Path, nodes):
            if self.is_filename_ignored(path.name):
                continue

            if path.is_dir():
                isbad = is_locked(str(path))
            else:
                isbad = not path.is_file()

            if isbad:
                imageindex = self.ICON_BAD
            elif path.is_dir():
                imageindex = self.ICON_DIR
            elif is_filename_mask_listed(path.name, MASKS_IMAGES):
                imageindex = self.ICON_IMG
            elif is_filename_mask_listed(path.name, MASKS_ZIP):
                imageindex = self.ICON_ZIP
            elif is_filename_mask_listed(path.name, MASKS_BINARY):
                imageindex = self.ICON_BIN
            else:
                lexname = lexer_proc(LEXER_DETECT, path.name)
                if lexname:
                    imageindex = self.icon_get(lexname)
                else:
                    imageindex = self.ICON_ALL

            index = tree_proc(
                self.tree,
                TREE_ITEM_ADD,
                parent,
                -1,
                path.name,
                imageindex
            )
            if nodes is self.project["nodes"]:
                self.top_nodes[index] = path

            if (imageindex == self.ICON_DIR) and (depth > 1):
                sub_nodes = sorted(path.iterdir(), key=Command.node_ordering)
                self.action_refresh(index, sub_nodes, depth - 1)

        if unfold:
            tree_proc(self.tree, TREE_ITEM_UNFOLD, parent)

    def action_new_project(self):
        self.new_project()
        self.action_refresh()

    def action_open_project(self, info=None):
        path = info
        if path is None:
            path = dlg_file(True, "", "", PROJECT_DIALOG_FILTER)
        if path:
            if Path(path).exists():
                print('Loading project: '+path)
                with open(path, encoding='utf8') as fin:
                    self.project = json.load(fin)
                    self.project_file_path = Path(path)
                    self.add_recent(path)
                    self.action_refresh()
                    self.save_options()

                self.update_global_data()
                msg_status("Project opened: " + path)
            else:
                msg_status("Recent item not found")

    def action_add_folder(self):
        self.add_node(lambda: dlg_dir(""))

    def action_add_file(self):
        self.add_node(lambda: dlg_file(True, "", "", ""))

    def action_remove_node(self):
        index = self.selected
        while index and index not in self.top_nodes:
            index = tree_proc(self.tree, TREE_ITEM_GET_PROPS, index)["parent"]

        if index in self.top_nodes:
            tree_proc(self.tree, TREE_ITEM_DELETE, index)
            path = self.top_nodes.pop(index)
            i = self.project["nodes"].index(str(path))
            self.project["nodes"].pop(i)
            if self.project_file_path:
                self.action_save_project_as(self.project_file_path)

    def action_clear_project(self):
        self.project["nodes"].clear()
        self.action_refresh()

    def action_set_as_main_file(self):
        path = self.get_location_by_index(self.selected)
        self.project["mainfile"] = str(path)
        self.update_global_data()

        if self.project_file_path:
            self.action_save_project_as(self.project_file_path)

    def action_save_project_as(self, path=None):
        need_refresh = path is None
        if path is None:
            if self.project_file_path:
                project_path = str(self.project_file_path.parent)
            else:
                project_path = ""
            path = dlg_file(False, "", project_path, PROJECT_DIALOG_FILTER)

        if path:
            path = Path(path)
            if path.suffix != PROJECT_EXTENSION:
                path = path.parent / (path.name + PROJECT_EXTENSION)

            self.project_file_path = path
            with path.open("w", encoding='utf8') as fout:
                json.dump(self.project, fout, indent=4)

            self.update_global_data()
            print('Saving project: '+str(path))
            msg_status("Project saved")

            if need_refresh:
                self.add_recent(str(path))
                self.action_refresh()
                self.save_options()

    def action_go_to_file(self):
        self.menu_goto()

    def action_project_properties(self):
        self.config_proj()

    def action_config(self):
        self.config()

    def update_global_data(self):
        global global_project_info
        global_project_info['filename'] = str(self.project_file_path) if self.project_file_path else ''
        global_project_info['nodes'] = self.project['nodes']
        global_project_info['vars'] = self.project.get('vars', [])
        global_project_info['mainfile'] = self.project.get('mainfile', '')

    def get_info(self, index):
        if index is None:
            return
        info = tree_proc(self.tree, TREE_ITEM_GET_PROPS, index)
        if info:
            return NodeInfo(info['text'], info['icon'])

    def get_location_by_index(self, index):
        path = []
        while index and index not in self.top_nodes:
            path.append(self.get_info(index).caption)
            index = tree_proc(self.tree, TREE_ITEM_GET_PROPS, index)['parent']

        path.reverse()
        node = self.top_nodes.get(index, None)
        full_path = Path(node / str.join(os.sep, path)) if node else Path('')

        return full_path


    def save_options(self):
        with self.options_filename.open(mode="w", encoding='utf8') as fout:
            json.dump(self.options, fout, indent=4)

    def menu_recents(self):
        items = self.options["recent_projects"]
        if not items:
            return

        items_nice = [os.path.basename(fn)+'\t'+os.path.dirname(fn) for fn in items]
        res = dlg_menu(MENU_LIST, '\n'.join(items_nice))
        if res is None:
            return

        self.init_panel()
        self.action_open_project(items[res])

    def do_unfold_first(self):
        """unfold 1st item under root"""
        items = tree_proc(self.tree, TREE_ITEM_ENUM, 0)
        if not items:
            return
        items = tree_proc(self.tree, TREE_ITEM_ENUM, items[0][0])
        if not items:
            return
        tree_proc(self.tree, TREE_ITEM_UNFOLD, items[0][0])
        tree_proc(self.tree, TREE_ITEM_SELECT, items[0][0])

    def new_project_open_dir(self):
        self.init_panel()
        self.action_new_project()
        self.action_add_folder()
        self.do_unfold_first()
        app_proc(PROC_SIDEPANEL_ACTIVATE, self.title)

    def open_dir(self, dirname, new_proj=False):
        if not os.path.isdir(dirname):
            return
        #expand "." to fully qualified name
        dirname = os.path.abspath(dirname)

        self.init_panel()
        if new_proj:
            self.action_new_project()
        self.add_node(lambda: dirname)
        if new_proj:
            self.do_unfold_first()

        app_proc(PROC_SIDEPANEL_ACTIVATE, self.title)

    def on_open_pre(self, ed_self, filename):
        if filename.endswith(PROJECT_EXTENSION):
            self.init_panel()
            self.action_open_project(filename)
            return False #block opening

    def config(self):
        if dialog_config(self.options):
            self.save_options()

            if self.h_dlg:
                dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, name='bar', prop={
                    'vis': self.options.get('toolbar', True)
                    })

    def config_proj(self):
        if not self.tree:
            msg_status('Project not loaded')
            return

        if dialog_proj_prop(self.project):
            self.update_global_data()
            if self.project_file_path:
                self.action_save_project_as(self.project_file_path)

    def is_filename_ignored(self, fn):
        mask_list = self.options.get("masks_ignore", MASKS_IGNORE)
        return is_filename_mask_listed(fn, mask_list)

    def on_start(self, ed_self):
        if not self.options.get("on_start", False):
            return

        and_activate = self.options.get("on_start_activate", False)
        self.init_panel(and_activate)

        items = self.options.get("recent_projects", [])
        if items:
            self.action_open_project(items[0])

    def contextmenu_add_dir(self):
        self.init_panel()
        self.action_add_folder()

    def contextmenu_add_file(self):
        self.init_panel()
        self.action_add_file()

    def contextmenu_new_proj(self):
        self.init_panel()
        self.action_new_project()

    def contextmenu_open_proj(self):
        self.init_panel()
        self.action_open_project()

    def contextmenu_save_proj_as(self):
        self.init_panel()
        self.action_save_project_as()

    def contextmenu_refresh(self):
        self.init_panel()
        self.action_refresh()

    def contextmenu_remove_node(self):
        self.init_panel()
        self.action_remove_node()

    def contextmenu_clear_proj(self):
        self.init_panel()
        self.action_clear_project()

    def contextmenu_set_as_main_file(self):
        self.init_panel()
        self.action_set_as_main_file()

    def enum_all(self, callback):
        """
        Callback for all items.
        Until callback gets false.
        """
        items = tree_proc(self.tree, TREE_ITEM_ENUM, 0)
        if items:
            return self.enum_subitems(items[0][0], callback)

    def enum_subitems(self, item, callback):
        """
        Callback for all subitems of given item.
        Until callback gets false.
        """
        items = tree_proc(self.tree, TREE_ITEM_ENUM, item)
        if items:
            for i in items:
                subitem = i[0]
                fn = str(self.get_location_by_index(subitem))
                if not callback(fn, subitem):
                    return False
                if not self.enum_subitems(subitem, callback):
                    return False
        return True

    def menu_goto(self):
        if not self.tree:
            msg_status('Project not opened')
            return

        #workaround: unfold all tree, coz tree loading is lazy
        #todo: dont unfold all, but allow enum_all() to work
        tree_proc(self.tree, TREE_ITEM_UNFOLD_DEEP, 0)

        files = []
        def callback_collect(fn, item):
            if os.path.isfile(fn):
                files.append(fn)
            return True

        self.enum_all(callback_collect)
        if not files:
            msg_status('Project is empty')
            return

        files_nice = [os.path.basename(fn)+'\t'+os.path.dirname(fn) for fn in files]
        res = dlg_menu(MENU_LIST_ALT, '\n'.join(files_nice))
        if res is None:
            return

        self.jump_to_filename(files[res])

    def jump_to_filename(self, filename):
        filename_to_find = filename

        def callback_find(fn, item):
            if fn==filename_to_find:
                tree_proc(self.tree, TREE_ITEM_SELECT, item)
                tree_proc(self.tree, TREE_ITEM_SHOW, item)

                #this focusing dont help, seems CudaText steals focus later
                self.focus_panel()
                #dlg_proc(self.h_dlg, DLG_FOCUS)

                if self.options.get('goto_open', False):
                    file_open(fn)

                return False
            return True

        msg_status('Jumping to: '+filename)
        return self.enum_all(callback_find)

    def sync_to_ed(self):
        if not self.tree:
            msg_status('Project not loaded')
            return

        fn = ed.get_filename()
        if fn:
            if self.jump_to_filename(fn): #gets False if found
                msg_status('Cannot jump to file: '+fn)


    def tree_on_unfold(self, id_dlg, id_ctl, data='', info=''):
        info = self.get_info(data)
        path = self.get_location_by_index(data)
        if info.image != self.ICON_DIR:
            return
        items = tree_proc(self.tree, TREE_ITEM_ENUM, data)
        if items:
            for handle, _ in items:
                tree_proc(self.tree, TREE_ITEM_DELETE, handle)
        sub_nodes = sorted(path.iterdir(), key=Command.node_ordering)
        self.action_refresh(data, sub_nodes)

    def tree_on_menu(self, id_dlg, id_ctl, data='', info=''):
        self.generate_context_menu()
        menu_proc(self.h_menu, MENU_SHOW, command='')


    def do_open_current_file(self, options):
        info = self.get_info(self.selected)
        if not info:
            return
        path = self.get_location_by_index(self.selected)
        if not path:
            return
        if info.image not in [self.ICON_BAD, self.ICON_DIR, self.ICON_PROJ]:
            file_open(str(path), options=options)

    def tree_on_click(self, id_dlg, id_ctl, data='', info=''):
        self.do_open_current_file('/preview')

    #def tree_on_click_dbl(self, id_dlg, id_ctl, data='', info=''):
    #    self.do_open_current_file('')


    def icon_init(self):

        self.icon_theme = self.options.get('icon_theme', 'vscode_16x16')

        try:
            nsize = int(re.match('^\w+x(\d+)$', self.icon_theme).group(1))
            imagelist_proc(self.tree_imglist, IMAGELIST_SET_SIZE, (nsize, nsize))
        except:
            print('Incorrect theme name, must be nnnnnn_NNxNN:', self.icon_theme)

        self.icon_dir = os.path.join(app_path(APP_DIR_DATA), 'filetypeicons', self.icon_theme)
        if not os.path.isdir(self.icon_dir):
            self.icon_dir = os.path.join(app_path(APP_DIR_DATA), 'filetypeicons', 'vscode_16x16')

        self.icon_json = os.path.join(self.icon_dir, 'icons.json')
        self.icon_json_dict = json.loads(open(self.icon_json).read())
        self.icon_indexes = {}


    def icon_get(self, key):

        s = self.icon_indexes.get(key, None)
        if s:
            return s

        fn = self.icon_json_dict.get(key, None)
        if fn is None:
            n = self.ICON_ALL
            self.icon_indexes[key] = n
            return n

        fn = os.path.join(self.icon_dir, fn)
        n = imagelist_proc(self.tree_imglist, IMAGELIST_ADD, value=fn)
        if n is None:
            print('Incorrect filetype icon:', fn)
            n = self.ICON_ALL
        self.icon_indexes[key] = n
        return n

    def form_key_down(self, id_dlg, id_ctl, data):

        if id_ctl==13: #Enter
            self.tree_on_click_dbl(id_dlg, id_ctl)
            return False #block key

    def add_current_file(self):

        if not self.tree:
            self.init_panel(False)

        fn = ed.get_filename()
        if fn:
            self.add_node(lambda: fn)

    def add_opened_files(self):

        if not self.tree:
            self.init_panel(False)

        for h in ed_handles():
            e = Editor(h)
            fn = e.get_filename()
            if fn:
                self.add_node(lambda: fn)


    def goto_main(self):
        if not self.tree:
            msg_status('Project not opened')
            return

        #workaround: unfold all tree, coz tree loading is lazy
        #todo: dont unfold all, but allow enum_all() to work
        tree_proc(self.tree, TREE_ITEM_UNFOLD_DEEP, 0)

        fn = self.project.get('mainfile', '')
        if not fn:
            msg_status('Project main file is not set')
            return
        self.jump_to_filename(fn)

    def open_main(self):
        fn = self.project.get('mainfile', '')
        if fn:
            file_open(fn)
        else:
            msg_status('Project main file is not set')
