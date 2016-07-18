import os
from cudatext import *

DEFAULT_MASKS_IGNORE = '*.zip *.7z *.tar *.gz *.rar *.exe *.dll .git .svn'

def dialog_config(op):

    id_ignore = 1
    id_recents = 3
    id_ok = 4
    
    c1 = chr(1)
    text = '\n'.join([]
        +[c1.join(['type=label', 'pos=6,6,500,0', 'cap=&File/folder masks to ignore (space-separated):'])]
        +[c1.join(['type=edit', 'pos=6,24,500,0', 'val='+op.get('masks_ignore', DEFAULT_MASKS_IGNORE)])]
        +[c1.join(['type=label', 'pos=6,54,500,0', 'cap=&Recent projects:'])]
        +[c1.join(['type=memo', 'pos=6,74,500,180', 'val='+'\t'.join(op.get('recent_projects', [])) ])]
        +[c1.join(['type=button', 'pos=300,300,400,0', 'cap=&OK', 'props=1'])]
        +[c1.join(['type=button', 'pos=406,300,506,0', 'cap=Cancel'])]
    )
    
    res = dlg_custom('Project Manager options', 512, 330, text)
    if res is None: 
        return
        
    res, text = res
    text = text.splitlines()
    
    if res != id_ok:
        return
        
    s = text[id_ignore].strip()
    while '  ' in s:
        s = s.replace('  ', ' ')
    op['masks_ignore'] = s
    
    s = text[id_recents].split('\t')
    op['recent_projects'] = s

    return True