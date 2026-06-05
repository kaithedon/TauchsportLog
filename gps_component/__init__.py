import os
import streamlit.components.v1 as components

# Declare the component
_component_func = components.declare_component(
    "gps_auto",
    path=os.path.dirname(os.path.abspath(__file__))
)

def get_gps_auto(key=None):
    """
    Returns the GPS coordinates as a dict: {'lat': float, 'lon': float}
    Returns None if waiting or if an error occurred.
    """
    return _component_func(key=key, default=None)
