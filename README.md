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
  Traffic-generation toolchain components, including IED configurations and supporting code used during simulation.

- `src/examples/`  
  Runnable examples demonstrating how to generate synthetic IEC 61850 traffic using SASMaker.

- `src/reference/`  
  Reference artifacts used during development and validation (e.g., example PCAPs, feature files, and analysis scripts).  
  These are not required for basic usage.

- `src/requirements.txt`  
  Python dependencies required to run SASMaker.

- `src/setup_venv_linux.sh`  
  Helper script for creating a Python virtual environment on Linux/macOS.

## Environment setup

SASMaker requires Python 3.10.x.

From the `src/` directory, create the virtual environment using the provided setup script:

```bash
./setup_venv_linux.sh
source venv/bin/activate
