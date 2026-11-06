"""Process-local experimental switches, captured once at startup."""
import os

BANGUMI_ENABLED = os.environ.get('ZHENXIA_ENABLE_BANGUMI') == '1'


def enable_bangumi():
    global BANGUMI_ENABLED
    BANGUMI_ENABLED = True
    # Download workers are separate processes and must inherit the startup choice.
    os.environ['ZHENXIA_ENABLE_BANGUMI'] = '1'
