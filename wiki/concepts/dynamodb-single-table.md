---
title: DynamoDB Single-Table Design
type: concept
tags: [dynamodb, aws, databases, architecture, patterns]
sources: [raw/admin_api_architecture_review.md]
created: 2026-04-17
updated: 2026-04-17
---

# DynamoDB Single-Table Design

A DynamoDB access pattern where all entity types share one table. Composite keys (`pk` + `sk`) identify items; Global Secondary Indexes (GSIs) support alternate access patterns without full table scans.

## Core Key Schema

```
pk  (partition key) = entity type + ID    e.g. APPLICATION#acme-devops-2026
sk  (sort key)      = item type + detail  e.g. METADATA | ANALYSIS#<ulid> | INTERVIEW#<stage>
```

Multiple items with the same `pk` but different `sk` represent related records for one entity (metadata, sub-records, counters).

## GSI Pattern for Status Queries

```
gsi1pk = ENTITY#<status>    e.g. APPLICATION#interviewing
gsi1sk = <date>#<slug>      e.g. 2026-04-15#acme-devops-2026
```

Allows `Query` on `gsi1pk = APPLICATION#interviewing` to list all interviewing applications — no table scan, no `FilterExpression` cost.

On status change, `UpdateItem` must update both `gsi1pk` (and `gsi1sk` if date changes) to keep the index consistent.

## admin-api Implementation

[[projects/admin-api]] uses this pattern for 4 entity types:

| Entity | `pk` format | `sk` variants | `gsi1pk` |
|---|---|---|---|
| Article | `ARTICLE#<slug>` | `METADATA`, `COUNTERS` | `ARTICLE#<status>` |
| Application | `APPLICATION#<slug>` | `METADATA`, `ANALYSIS#<ulid>`, `INTERVIEW#<stage>` | `APPLICATION#<status>` |
| Resume | `RESUME#<uuid>` | `METADATA` | `RESUME#active` or `RESUME#inactive` |
| Comment | `ARTICLE#<slug>` | `COMMENT#<ts>#<uuid>` | `COMMENT#pending` |

## Access Patterns Met

| Operation | Method | Cost |
|---|---|---|
| Get one item | `GetItem(pk, sk)` | Cheap — exact key lookup |
| List by status | `Query(GSI, gsi1pk = STATUS#x)` | Cheap — index read, no scan |
| All items for entity | `Query(pk = ENTITY#slug)` | Cheap — all sk variants |
| Batch delete entity | `BatchWriteItem` on all sk variants | Efficient — one call |
| Full table list | `Scan` | Expensive — avoid |

## Atomicity Risk: Non-Transactional Updates

Two-step operations (deactivate old → activate new) require `TransactWriteCommand` to be safe. Sequential `UpdateItem` calls leave a window where inconsistent state is visible if the process crashes between them.

Example: resume activation in [[projects/admin-api]] uses two separate `UpdateItem` calls — known issue, fix is `TransactWriteCommand`:

```typescript
await client.send(new TransactWriteCommand({
  TransactItems: [
    { Update: { /* deactivate previous active resume */ } },
    { Update: { /* activate new resume */ } },
  ],
}));
```

## Counter Pattern

Counter items (`sk = COUNTERS`) use `UpdateExpression: 'ADD commentCount :inc'` for atomic increment. The DynamoDB ADD operation is atomic per-item but NOT atomic with a separate status update — combine with `TransactWriteCommand` when both must succeed together.

## Batch Delete Pattern

When deleting an entity, all sort-key variants must be deleted together to avoid orphaned records:

```typescript
const deleteRequests = allSkVariants.map(sk => ({
  DeleteRequest: { Key: { pk: `APPLICATION#${slug}`, sk } }
}));
await client.send(new BatchWriteItemCommand({ RequestItems: { [TABLE]: deleteRequests } }));
```

## Related Pages

- [[projects/admin-api]] — uses this pattern for articles, applications, resumes, comments
- [[ai-engineering/job-strategist]] — uses same single-table for APPLICATION# records
- [[tools/aws-bedrock]] — DynamoDB used by job strategist pipeline for analysis persistence
