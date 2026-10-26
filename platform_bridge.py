import sys
if sys.platform == 'darwin':
    from macos_integration import (capture_selection, replace_selection, same_text,
                                   foreground_is_ours, set_startup, startup_enabled)
else:
    from windows_integration import (capture_selection, replace_selection, same_text,
                                     foreground_is_ours, set_startup, startup_enabled)
