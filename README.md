# DevOps Agent 🤖⚙️

An AI-powered DevOps agent designed to interact with Linux systems through controlled, auditable and approval-aware tooling.

The project is being developed as a practical DevOps + AI engineering project, with a strong focus on **automation, reliability, security, observability and human approval**.

---

## 🚀 Overview

**DevOps Agent** is an AI-driven agent that can reason about operational tasks and interact with a Linux environment through a controlled tool system.

Instead of allowing an LLM to execute arbitrary commands directly, the project is built around a structured architecture:

```text
                    ┌─────────────────────┐
                    │       User          │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Agent / LLM      │
                    │     Reasoning       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Tool Registry     │
                    │                     │
                    │  Available Tools    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Approval / Policy   │
                    │       Layer         │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Linux System     │
                    └─────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Audit / Reliability │
                    │      Layer          │
                    └─────────────────────┘
```

The goal is to create an agent that can perform useful operational work **without turning the LLM into an unrestricted shell executor**.

---

## 🎯 Project Goals

The main goals of the project are:

* Build a practical AI-powered DevOps assistant
* Execute operational tasks through controlled tools
* Separate reasoning from execution
* Introduce human approval for sensitive operations
* Maintain an audit trail of agent actions
* Improve reliability through testing and validation
* Provide a modular tool architecture
* Make the system extensible with new DevOps capabilities
* Learn how AI agents can safely interact with infrastructure

---

## 🧠 Core Architecture

The project is intentionally divided into several components.

### Agent

`agent.py`

The main orchestration layer responsible for coordinating the agent workflow.

It connects reasoning, context, tools and execution.

---

### LLM Layer

`llm.py`

Provides the interface between the agent and the language model.

The goal is to keep model-specific logic separated from the rest of the application.

This makes it possible to change or extend the underlying model without rewriting the entire agent.

---

### Context

`context.py`

Responsible for maintaining the context required by the agent while it reasons about a task.

Context management is important because an operational agent needs to understand:

* what the user requested
* what has already happened
* what tools are available
* what information was returned
* what action should happen next

---

### Tool Registry

`tool_registry.py`

Provides a central registry for available agent tools.

Instead of allowing the LLM to execute arbitrary system commands, the agent works with explicitly registered capabilities.

Conceptually:

```text
LLM
 │
 ├── list_files
 ├── read_file
 ├── system_info
 ├── web_fetch
 └── other registered tools
```

This creates a controlled boundary between AI reasoning and real-world execution.

---

### Tools

`tools/`

Contains the actual tools available to the agent.

The architecture is designed so that new capabilities can be added independently without turning `agent.py` into a monolithic application.

---

### Approval Layer

`approval.py`

Sensitive actions should not necessarily be executed immediately.

The approval layer provides a mechanism for separating:

```text
Agent decision
      ↓
Approval
      ↓
Execution
```

This is an important safety principle for infrastructure automation.

A future production implementation can use policies to determine which operations require approval and which can execute automatically.

---

### Audit

The project includes auditing functionality for tracking agent operations.

Auditability is important for DevOps automation because an operator should be able to answer:

* What did the agent do?
* Why did it do it?
* Which tool was executed?
* What was the result?
* When did the operation happen?

---

## 🧪 Testing

The project includes tests covering several areas of the agent.

Current test modules include:

```text
test_orchestration.py
test_registry.py
test_reliability.py
test_web.py
test_web_fetch.py
```

Testing is an important part of the project because an AI agent should not be considered reliable simply because the underlying LLM produces reasonable responses.

The goal is to validate the deterministic parts of the system independently.

---

## 🔐 Security Principles

Security is a core design consideration.

The project follows several principles:

### Least Privilege

Tools should only have the permissions required to perform their intended operation.

### Explicit Capabilities

The LLM should interact with registered tools rather than receiving unrestricted system access.

### Human-in-the-Loop

Potentially destructive or sensitive operations can require explicit approval.

### Secrets Protection

Secrets and environment-specific configuration should not be committed to Git.

For example:

```text
.env
.venv/
__pycache__/
*.pyc
.DS_Store
```

are excluded through `.gitignore`.

### Auditability

Important operations should be traceable through audit information.

---

## 📁 Project Structure

```text
devops-agent/
│
├── agent.py
├── approval.py
├── audit.py
├── config.py
├── context.py
├── llm.py
├── tool_registry.py
│
├── tools/
│   └── ...
│
├── ui/
│   └── ...
│
├── tests/
│   └── ...
│
├── test_orchestration.py
├── test_registry.py
├── test_reliability.py
├── test_web.py
├── test_web_fetch.py
│
├── AUDIT_REPORT.md
├── .gitignore
└── README.md
```

---

## ⚙️ Development Environment

The project is developed using Python and a virtual environment.

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install project dependencies:

```bash
pip install -r requirements.txt
```

> If `requirements.txt` is not yet present, dependencies should be documented as the project evolves.

---

## ▶️ Running the Agent

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Then run the agent entry point:

```bash
python agent.py
```

The exact execution flow may evolve as the architecture develops.

---

## 🧪 Running Tests

Run the test suite with:

```bash
pytest
```

For more detailed output:

```bash
pytest -v
```

---

## 🔭 Roadmap

The project is under active development.

Planned areas include:

* [ ] More DevOps-specific tools
* [ ] Better tool permission policies
* [ ] Advanced approval workflows
* [ ] Improved audit logging
* [ ] Persistent agent memory/context
* [ ] Infrastructure diagnostics
* [ ] Docker integration
* [ ] Kubernetes integration
* [ ] System health monitoring
* [ ] Remote server management
* [ ] CI/CD integration
* [ ] Observability integration
* [ ] Web-based management interface
* [ ] Better failure recovery
* [ ] Production-grade security model

---

## 🏗️ Design Philosophy

The project is based on a simple principle:

> **An AI agent should not be trusted simply because it is intelligent. It should be designed so that its actions are controlled, observable and reversible whenever possible.**

The long-term goal is not just to build another chatbot.

The goal is to build an **operational AI system** that can reason about infrastructure, interact with real systems through controlled interfaces, explain its actions and remain accountable for what it does.

---

## 📌 Project Status

**Status:** Active Development 🚧

This project is currently being developed as an experimental AI + DevOps engineering system.

Architecture, APIs and tool interfaces may change as the project evolves.

---

## 👤 Author

**Shotiko R.**

Building and experimenting with:

* DevOps
* Linux
* Python
* Docker
* Kubernetes
* AI Agents
* Infrastructure Automation
* Security
* Observability

---

## 📄 License

License information will be added as the project matures.
