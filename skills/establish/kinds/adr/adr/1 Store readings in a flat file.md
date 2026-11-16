---
kind: adr
id: 1
title: Store readings in a flat file
status: superseded
date: 2026-03-02
superseded_by: "[[2 Store readings in SQLite]]"
---
# Store readings in a flat file

## Context

The Lantern weather station logs one reading a minute. A single station needs no query language, and a flat file is easy to inspect.

## Decision

Append each reading as one CSV line to a file per day.

## Consequences

Cheap to write and to read by hand. Averages across weeks mean scanning many files, which is why a later decision replaced this one.
