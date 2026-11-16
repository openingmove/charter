---
kind: adr
id: 2
title: Store readings in SQLite
status: accepted
date: 2026-06-18
---
# Store readings in SQLite

## Context

Two stations now report to one hub, and the weekly averages need readings from both. [[1 Store readings in a flat file]] made that slow.

## Decision

Keep every reading in one SQLite database on the hub.

## Consequences

Averages and gaps become single queries. The hub gains one file to back up.
