# CCF Systems Dashboard Documentation

This directory contains the active development, architecture, operations, and
roadmap documentation for the CCF Systems Dashboard. Project setup and the
high-level feature summary remain in the repository-level [README](../README.md).

## Architecture and technical references

- [Technical Reference](TECHNICAL_REFERENCE.md)
- [Current Database Structure](CURRENT_DATABASE_STRUCTURE.md)
- [Registrant and Satellite Curation](CURATION_LAYER.md)
- [Age Distribution Logic](AGE_DISTRIBUTION_LOGIC.md)

## Application modules

- [Event Dashboard](DASHBOARD_MODULE.md)
- [Phase 1 Core Event Dashboard](PHASE_1_CORE_DASHBOARD.md)
- [Event Imports](EVENT_IMPORTS_MODULE.md)
- [Data Quality](DATA_QUALITY_MODULE.md)
- [Satellite Analytics](SATELLITE_ANALYTICS_MODULE.md)
- [Admin Tables](ADMIN_TABLES_MODULE.md)
- [Admin Tables Query Reference](ADMIN_TABLES_QUERY_REFERENCE.md)
- [Registrations](REGISTRATIONS_MODULE.md)
- [Registrations Three-Phase Plan](REGISTRATIONS_MODULE_3_PHASE_PLAN.md)
- [Authentication and User Approval](AUTHENTICATION.md)
- [Advanced Analytics Reference](ANALYTICS_REFERENCE.md)
- [Reporting and Export Governance](REPORTING.md)

## Project phases and decisions

- [Phase Checklists](PHASE_CHECKLISTS.md)
- [Phase 2 Decisions](PHASE_2_DECISIONS.md)
- [Phase 2 Verification](PHASE_2_VERIFICATION.md)
- [Phase 3 Decisions](PHASE_3_DECISIONS.md)

## Production operations

- [Deployment Runbook](DEPLOYMENT_RUNBOOK.md)
- [Rollback Runbook](ROLLBACK_RUNBOOK.md)
- [Backup and Recovery](BACKUP_AND_RECOVERY.md)
- [Operations and Incident Response](OPERATIONS_AND_INCIDENT_RESPONSE.md)
- [Production Acceptance and UAT](PRODUCTION_ACCEPTANCE.md)
- [Target-Environment Security Validation](TARGET_SECURITY_VALIDATION.md)

## Documentation policy

- Keep current operating instructions and implemented behavior in this
  directory.
- Keep `README.md` at the repository root as the project entry point.
- Update existing documents instead of creating contradictory replacements.
- Remove obsolete proposal or implementation notes once their useful content is
  represented in the authoritative references and Git history.
