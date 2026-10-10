#!/usr/bin/env python3
"""Ponto de entrada do backend (os apps nativos rodam este arquivo). O código mora no pacote pilot/."""
import os
import sys

# O Python embutido do Windows (._pth) não põe a pasta do script no sys.path: garante que o pacote seja achado.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pilot.http import main  # noqa: E402

if __name__ == "__main__":
    main()
