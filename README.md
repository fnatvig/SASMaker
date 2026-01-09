# SASMaker

SASMaker is a framework for generating synthetic IEC 61850 network traffic from diverse substation setups. It supports constructing modeled substations and producing PCAP traces that can be used for downstream cybersecurity and intrusion-detection research.

This repository accompanies the paper:

**SASMaker: A Framework for Generating Synthetic IEC 61850 Traffic from Diverse Substation Setups** *(submitted to CIGRE Paris Session 2026)*

## Overview

The purpose of SASMaker is to enable controlled generation of IEC 61850 traffic by modeling substation components and communication behavior. The framework is intended to support research on intrusion detection, data generation, and evaluation of cybersecurity methods in IEC 61850-based substations.

This repository focuses on **synthetic traffic generation**. Feature extraction, machine-learning training, and evaluation are intentionally handled in a separate repository to keep dataset generation and analysis clearly decoupled.

## Repository structure

- `src/sasmaker/`  
  Core SASMaker source code, including substation modeling, simulation logic, and utility functions.

- `src/toolchain/`  
  Integrated IEC 61850 traffic-generation toolchain components adapted from an external open-source toolchain and prior work, including IED configurations and supporting code used during simulation (see `src/README.md` for details).

- `src/examples/`  
  Runnable examples demonstrating how to generate synthetic IEC 61850 traffic using SASMaker.

- `src/reference/`  
  Reference artifacts used during development and validation (e.g., example PCAPs, feature files, and analysis scripts).  
  These are not required for basic usage.

- `src/requirements.txt`  
  Python dependencies required to run SASMaker.

- `src/setup_venv_linux.sh`  
  Helper script for creating a Python virtual environment on Linux/macOS.

## Related repositories

**Machine-learning evaluation and result reproduction**
https://github.com/fnatvig/SASMakerEval

This repository contains the scripts and instructions required to reproduce the machine-learning evaluation results reported in the paper. It operates on pre-generated feature files derived from SASMaker-generated and reference PCAPs.

## Reference

If you use SASMaker in academic work, please cite the corresponding paper:

**SASMaker: A Framework for Generating Synthetic IEC 61850 Traffic from Diverse Substation Setups** *(submitted to CIGRE Paris Session 2026)*

