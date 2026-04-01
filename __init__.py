# -*- coding: utf-8 -*-
# Archaeological Sites Visualizer - QGIS Plugin
#
# Visualization, annotation and validation of archaeological sites
# in georeferenced aerial images.
#
# This script initializes the plugin and is required by QGIS to
# load it. It defines the classFactory function that QGIS calls
# to instantiate the plugin.


def classFactory(iface):
    # Required entry point for all QGIS plugins.
    # :param iface: A QGIS interface instance (QgisInterface).
    # :returns: ArchaeologicalSitesVisualizer instance.
    from .plugin import ArchaeologicalSitesVisualizer
    return ArchaeologicalSitesVisualizer(iface)
