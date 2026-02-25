# Active PEPs

Quick reference of all PEPs currently in the workflow. Update this table when a PEP changes status. Remove rows when a PEP is moved to [IMPLEMENTED/LATEST.md](IMPLEMENTED/LATEST.md).

| PEP  | Title                          | Status   | Effort | Risk   | Depends On |
|------|--------------------------------|----------|--------|--------|------------|
| 0002 | Rename FileUpload to IngestFile | Implementing | M      | Medium | —          |
| 0003 | Extend Data Models              | Proposed | M      | Medium | 0002       |

## Dependency Graph

```mermaid
graph TD
    PEP0002["🟡 0002: Rename FileUpload to IngestFile"]
    PEP0003["🟡 0003: Extend Data Models"]
    PEP0003 --> PEP0002
```

**Legend:** 🔴 High risk | 🟡 Medium risk | 🟢 Low risk
