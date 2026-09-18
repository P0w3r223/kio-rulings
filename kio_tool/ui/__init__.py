"""Warstwa użytkownika: `texts.py` — zdania dla operatora (reguła 9), `render.py` — rysowanie
modeli widoku przez `rich` (reguła 10).

`ui/*` nie importuje `source` ani `store` (reguła 8); idzie przez `pipeline`. Kreator
(`wizard.py`, `flow.py`, `prompts.py`) jest fazą 3 i nie powstał — `cli.py` woła `texts`
i `ConsoleView` wprost.
"""
