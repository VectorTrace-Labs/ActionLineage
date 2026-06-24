# API Reference

This reference lists the alpha-supported public Python imports for
ActionLineage. Import from `actionlineage` unless a lower-level module is
explicitly needed.

## Core Event Model

- `EventEnvelope`, `EventType`
- `Correlation`, `Causality`, `Source`, `Principal`
- `Classification`, `Sensitivity`, `TrustLevel`
- `EvidenceLink`, `EvidenceRelationship`, `VerificationStatus`
- `parse_event`, `serialize_event`, `event_to_dict`
- `CANONICALIZATION_VERSION`, `PLANNED_CANONICALIZATION_VERSION`
- `SUPPORTED_PERSISTED_EVENT_CANONICALIZATIONS`,
  `persisted_event_canonicalization_policy`
- `is_supported_persisted_event_canonicalization`,
  `require_supported_persisted_event_canonicalization`

## Ingestion and Normalization

- `EvidenceRecord`, `EvidenceNormalizer`, `EvidenceSourceKind`
- `NormalizedAction`, `NormalizedResource`, `ToolIdentity`
- `DelegatedIdentity`, `ObservationRecord`, `VerificationRecord`
- `import_evidence_batch`, `collect_records`

## Journal and Projection

- `LocalJournal`, `verify_journal`
- `JournalAnchor`, `create_journal_anchor`, `verify_journal_anchor`
- `append_journal_anchor_log`, `verify_journal_anchor_log`
- `GitAnchorStatement`, `create_git_anchor_statement`,
  `verify_git_anchor_statement`
- `ExternalAnchorAttestation`, `create_external_anchor_attestation`,
  `verify_external_anchor_attestation`
- `JournalArchiveManifest`, `create_journal_archive_manifest`,
  `verify_journal_archive_manifest`
- `query_timeline`, `query_filtered_timeline`, `export_incident`
- `explain_event`, `export_case_bundle`
- `summarize_incident`, `GroundedInvestigationSummary`
- `export_investigation_graph`, `InvestigationGraphExport`
- `rebuild_postgres_projection`, `verify_postgres_projection_state`,
  `postgres_schema_statements`

## Detection, Contracts, and Lab

- `SequenceRule`, `built_in_sequence_rules`, `evaluate_sequence_rule`
- `explain_sequence_rule`, `RuleExplanation`, `GroupExplanation`, `StageExplanation`
- `load_sequence_rules`, `sequence_rule_from_dict`, `sequence_rule_to_dict`
- `DetectionRuleLoadError`
- `LineageContract`, `load_contract`, `validate_contract`
- `ReplayCase`, `MutationStrategy`, `score_detection_robustness`
- `ExtensionPackManifest`, `PackArtifact`, `validate_pack_manifest`
- `load_pack_manifest`, `pack_artifact_index`

## Observers, Exporters, Service, and Console

These imports are available in the alpha package, but service, cloud,
OpenTelemetry, MCP, and deployment-oriented surfaces are preview APIs until
external validation and production operating guidance are complete.

- `FilesystemObserver`, `MockHttpReceiverObserver`, `HttpServerLogObserver`
- `HttpResponseReadbackObserver`
- `WebhookReceiptObserver`
- `ProcessObserver`
- `SqliteReadbackObserver`
- `AwsCloudTrailObserver`, `GcpAuditLogObserver`, `AzureActivityObserver`
- `KubernetesAuditObserver`
- `ExternalSensorDeclaration`, `ExternalSensorFeedObserver`, `ExternalSensorKind`
- `ExternalSensorObservationRecord`
- `ObserverAttestationDeclaration`, `AttestationEvidenceKind`
- `IndependenceBoundary`, `IndependenceBoundaryStatus`
- `ObserverAttestationError`, `observer_attestation_declaration_from_dict`
- `independent_claim_rejection_reasons`,
  `require_independent_observer_attestation`
- `verify_observation`, `self_reported_verification`
- `ExportProfile`, `export_events`, `otel_attributes_for_event`
- `otel_attributes_for_redacted_event`
- `OpenTelemetrySpanSink`, `OpenTelemetryExporterUnavailable`
- `TaxiiHttpSink`, `taxii_envelope_for_stix_bundle`
- `StaticTokenAuthenticator`, `JwtAuthenticator`, `OidcJwtAuthenticator`
- `ServiceTenant`, `TenantRegistry`, `TenantRoleBinding`
- `require_tenant_role`
- `check_local_health`, `create_app`
- `create_service_app_from_env`
- `ConsoleExport`, `ConsoleNote`, `ConsoleSavedView`
- `DesktopBundleExport`, `write_desktop_bundle`
- `console_context_from_dict`, `load_console_context`
- `write_console`, `render_console_html`

## Adapter Boundaries

Import optional adapter helpers from `actionlineage.adapters` when they are not
part of the core top-level API:

- `FrameworkKind`, `FrameworkToolDescriptor`, `FrameworkToolInvocation`
- `FrameworkAcknowledgementStatus`, `framework_lifecycle_records`
- `framework_descriptor_hash`, `framework_tool_identity`
- `McpSdkClient`, `McpStreamableHttpClientConfig`, `McpStdioClientConfig`
- `descriptor_from_sdk_tool`, `downstream_result_from_sdk_call_result`

## Compatibility

The `actionlineage.dev/v1alpha1` envelope is the supported alpha read boundary.
Unknown event types are preserved but not interpreted as safe behavior. See
`docs/COMPATIBILITY.md` for migration policy.
