#!/usr/bin/env python3
"""
Mercy AI Interface Package
Complete GUI interface for Mercy AI assistant
"""

__version__ = '1.0.0'
__author__ = 'Mercy AI Team'

from .interface import MercyInterface
from .brain_connector import BrainConnector

__all__ = ['MercyInterface', 'BrainConnector']
