# Project Objectives

## Mission

Build a reliable manager layer that coordinates AI coding-agent workflows from a single task interface, while preserving human review and operational safety.

## Problem this project solves

Teams experimenting with coding agents often face fragmented tooling, unclear task state, and weak auditability. This project provides a unified workflow from intent to review-ready output.

## Core goals

- Convert plain-English goals into structured, trackable tasks.
- Execute local or SSH-based development actions in a controlled way.
- Persist task state, events, and outputs for traceability.
- Produce branch-scoped changes that are easy to review and merge.
- Expose simple APIs and UI so beginners can adopt quickly.

## Non-goals (current MVP)

- Full autonomous merge-to-production without human approval.
- Advanced enterprise IAM and multi-tenant authorization models.
- Provider-specific deep optimization for every AI coding platform.

## Phased roadmap

1. MVP foundation: task lifecycle, execution primitives, persistence, and basic UI.
2. Review workflow: commit helpers, PR draft generation, and GitHub integration hardening.
3. Reliability: richer retry logic, stronger sandboxing, broader test coverage, and observability improvements.
4. Extensibility: pluggable provider adapters and policy-driven orchestration rules.

## How to evaluate progress

- Time-to-first-task remains short for new contributors.
- Task status and audit trails are clear and complete.
- Failures are diagnosable from logs/events without guesswork.
- Reviewers can inspect diffs and test outcomes before accepting changes.
