#Create and activate a virtual environment ( If needed)
  python -m venv .venv
  source .venv/bin/activate

#Install dependencies
  pip install -r requirements.txt

#Run the Dashboard
  Python app.py

#open the browser
  http://127.0.0.1:8050


  # CoinsApp Dashboard

Interactive Dash-based dashboard for mass spectrometry (MS) feature analysis of the
final products **Hepar** and **Hepeel**, with  comparison against plant and
animal raw components.

This repository contains the full analysis pipeline and dashboard used for exploratory
and comparative MS feature analysis.

---

## Feature origin definitions

Let:

- **P** = MS features detected in the final product  
- **Pl** = MS features detected in at least one plant component  
- **An** = MS features detected in at least one animal component  

### Common (plant + animal) 
P ∩ Pl ∩ An

### Product-only
P − (Pl ∪ An)

Componenet-Only
(Pl ∪ An) − P
