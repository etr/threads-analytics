---
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Glob, Grep, Skill
description: Find Threads posts that may interest you, based on your posting history and optional seed topics.
user-invocable: true
argument-hint: "[days] [--seeds \"topic1, topic2\"] [--recent] [--refresh]"
---

Use the Skill tool to invoke the `threads-analytics:threads-recommendations` skill with these arguments: $ARGUMENTS
