# SASMaker (ISGT Dataset Reproduction)

This branch of **SASMaker** reproduces the datasets used in the paper:

**“When Flooding Looks Legitimate: Evaluating Intrusion Detection under Stealthy GOOSE Attacks”** *(submitted to IEEE ISGT Europe 2026)*

## Overview

This branch generates the PCAP traces used to evaluate intrusion detection systems under **stealthy GOOSE flooding attacks**.

The datasets include:
- One benign training trace  
- Three evaluation traces corresponding to attacker levels:
  - Level 1 (naive)  
  - Level 2 (multi-stream)  
  - Level 3 (bus-aware)  

All traces share the same switching scenario to isolate the effect of attacker sophistication.

## Usage

Run the configurations in `src/examples/` to reproduce the datasets used in the paper.

## Repository structure

- `src/sasmaker/` – Core SASMaker source code, including substation modeling, simulation logic, and utility functions.
- `src/toolchain/` – Integrated IEC 61850 traffic-generation toolchain components adapted from an external open-source toolchain and prior work, including IED configurations and supporting code used during simulation (see https://github.com/smartgridadsc/IEC61850ToolChain for details).
- `src/examples/` – Dataset generation scripts  

## Related repository

Machine-learning evaluation and result reproduction:  
https://github.com/fnatvig/Stealthy-GOOSE-IDS-Evaluation