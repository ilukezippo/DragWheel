"""DragWheel's main program, in parts by feature.

They are not separate modules: dragwheel.pyw runs them one after another in its own namespace
(see load_parts there), so they share everything, exactly as when they were one file. Each part can use
what the parts before it define at import time, and anything at all when its functions run.
"""
