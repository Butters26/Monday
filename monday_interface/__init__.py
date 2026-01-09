#!/usr/bin/env python3
"""
Monday AI Interface Package
Complete GUI interface for Monday AI assistant
"""

__version__ = '1.0.0'
__author__ = 'Monday AI Team'

from .interface import MondayInterface
from .brain_connector import BrainConnector

__all__ = ['MondayInterface', 'BrainConnector']
