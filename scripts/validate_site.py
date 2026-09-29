#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_site.py — Compatibilidade: agora valida o monitor UE exclusivo.

Este repositório é exclusivo UE em https://monitor-ue.vercel.app/.
O validador brasileiro legado foi substituído por validate_site_eu.py.
Este arquivo apenas redireciona para o validador UE para não quebrar
workflows ou scripts que ainda chamam validate_site.py.
"""
import sys
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))
import validate_site_eu as _eu
if __name__ == "__main__":
    sys.exit(_eu.main())
