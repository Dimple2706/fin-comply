import { useCallback, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useDropzone } from 'react-dropzone';
import {
  HiOutlineArrowPath,
  HiOutlineArrowRight,
  HiOutlineArrowsRightLeft,
  HiOutlineCheckCircle,
  HiOutlineCircleStack,
  HiOutlineClipboardDocumentCheck,
  HiOutlineClock,
  HiOutlineCloudArrowUp,
  HiOutlineDocumentText,
  HiOutlineKey,
  HiOutlineLockClosed,
  HiOutlineScale,
  HiOutlineServer,
  HiOutlineShieldCheck,
  HiOutlineUsers,
  HiOutlineXMark,
} from 'react-icons/hi2';
import { getStoredUser, runAnalysis, runAnalysisExisting } from '../services/api';
import { clearTermsAcceptance, getTermsAcceptance, TERMS_VERSION } from '../utils/termsAcceptance';
import TermsGate from '../components/onboarding/TermsGate';
import TermsModal from '../components/onboarding/TermsModal';

const FILE_TYPES = [
  { id: 'governance_config', label: 'Governance', description: 'Roles, contacts and oversight', icon: HiOutlineShieldCheck },
  { id: 'customer_master', label: 'Customers', description: 'Customer profile evidence', icon: HiOutlineUsers },
  { id: 'consent_records', label: 'Consent', description: 'Notices and consent status', icon: HiOutlineClipboardDocumentCheck },
  { id: 'transaction_events', label: 'Processing activity', description: 'Purpose and data-use events', icon: HiOutlineArrowsRightLeft },
  { id: 'access_logs', label: 'Access history', description: 'Who accessed which records', icon: HiOutlineKey },
  { id: 'data_lifecycle', label: 'Data lifecycle', description: 'Retention and deletion evidence', icon: HiOutlineClock },
  { id: 'security_events', label: 'Security events', description: 'Incident and response records', icon: HiOutlineLockClosed },
  { id: 'dsar_requests', label: 'Rights requests', description: 'Requests and response dates', icon: HiOutlineDocumentText },
  { id: 'system_inventory', label: 'Systems', description: 'Applications and data locations', icon: HiOutlineServer },
  { id: 'policies', label: 'Policies', description: 'Internal controls and approvals', icon: HiOutlineScale },
];

function Brand() {
  return (
    <div className="fin-brand">
      <span className="fin-brand-mark"><HiOutlineShieldCheck aria-hidden="true" /></span>
      <span className="fin-brand-copy">
        <strong>FinComply</strong>
        <small>DPDP readiness workspace</small>
      </span>
    </div>
  );
}

function FileZone({ type, file, onDrop, onRemove }) {
  const Icon = type.icon;
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted) => accepted[0] && onDrop(type.id, accepted[0]),
    accept: { 'text/csv': ['.csv'] },
    maxFiles: 1,
    multiple: false,
  });

  if (file) {
    return (
      <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="file-tile complete px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="h-9 w-9 rounded-xl grid place-items-center bg-green-600/10 text-low flex-shrink-0"><HiOutlineCheckCircle aria-hidden="true" /></span>
          <span className="min-w-0">
            <strong className="block text-xs text-primary truncate">{file.name}</strong>
            <small className="block mt-1 text-[10px] text-muted">{type.label} · ready</small>
          </span>
        </div>
        <button type="button" onClick={() => onRemove(type.id)} aria-label={`Remove ${type.label} file`} className="p-2 rounded-lg text-muted hover:text-critical hover:bg-red-50 transition-colors">
          <HiOutlineXMark aria-hidden="true" />
        </button>
      </motion.div>
    );
  }

  return (
    <div {...getRootProps()} className={`file-tile px-4 py-3 flex items-center justify-between gap-3 cursor-pointer ${isDragActive ? 'dragging' : ''}`}>
      <input {...getInputProps()} aria-label={`Upload ${type.id}.csv`} />
      <div className="flex items-center gap-3 min-w-0">
        <span className="h-9 w-9 rounded-xl grid place-items-center bg-brand-primary/10 text-brand-primary flex-shrink-0"><Icon aria-hidden="true" /></span>
        <span className="min-w-0">
          <strong className="block text-xs text-primary">{type.label}</strong>
          <small className="block mt-1 text-[10px] text-muted truncate">{type.id}.csv · {type.description}</small>
        </span>
      </div>
      <HiOutlineCloudArrowUp className="text-lg text-copper flex-shrink-0" aria-hidden="true" />
    </div>
  );
}

export default function Onboarding({ onComplete, user, onLogout }) {
  const [termsAccepted, setTermsAccepted] = useState(() => getTermsAcceptance());
  const [showTermsModal, setShowTermsModal] = useState(false);
  const [mode, setMode] = useState('existing');
  const [existingTenantId, setExistingTenantId] = useState(() => getStoredUser()?.tenant_id || '');
  const [orgName, setOrgName] = useState('');
  const [tenantId, setTenantId] = useState(() => getStoredUser()?.tenant_id || '');
  const [files, setFiles] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleTermsReset = useCallback(() => {
    clearTermsAcceptance();
    setTermsAccepted(false);
  }, []);

  const handleDrop = useCallback((typeId, file) => {
    setFiles((current) => ({ ...current, [typeId]: file }));
  }, []);

  const handleRemove = useCallback((typeId) => {
    setFiles((current) => {
      const next = { ...current };
      delete next[typeId];
      return next;
    });
  }, []);

  const fileCount = Object.keys(files).length;
  const isUploadReady = fileCount === FILE_TYPES.length && Boolean(orgName.trim()) && Boolean(tenantId.trim());
  const isExistingReady = Boolean(existingTenantId.trim());

  const handleRunExisting = async () => {
    if (!isExistingReady || loading) return;
    setLoading(true);
    setError(null);
    try {
      onComplete(await runAnalysisExisting(existingTenantId.trim()));
    } catch (requestError) {
      setError(requestError.message);
      setLoading(false);
    }
  };

  const handleRunUpload = async () => {
    if (!isUploadReady || loading) return;
    setLoading(true);
    setError(null);
    const formData = new FormData();
    formData.append('tenant_name', orgName.trim());
    formData.append('tenant_id', tenantId.trim());
    Object.entries(files).forEach(([key, file]) => formData.append(key, file));
    try {
      onComplete(await runAnalysis(formData));
    } catch (requestError) {
      setError(requestError.message);
      setLoading(false);
    }
  };

  if (!termsAccepted) {
    return (
      <AnimatePresence mode="wait">
        <TermsGate onAccept={() => setTermsAccepted(true)} user={user} onLogout={onLogout} />
      </AnimatePresence>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fin-shell">
      {loading && (
        <div className="fixed inset-0 z-50 bg-[#261e2b]/90 backdrop-blur-md flex flex-col items-center justify-center px-6 text-center" role="status" aria-live="polite">
          <div className="h-14 w-14 rounded-2xl border border-white/15 bg-white/10 grid place-items-center mb-5">
            <HiOutlineArrowPath className="text-2xl text-[#dabf9f] animate-spin" aria-hidden="true" />
          </div>
          <h2 className="text-2xl font-semibold text-[#fffaf3]">Building your compliance assessment</h2>
          <p className="mt-2 max-w-md text-sm leading-6 text-[#fffaf3]/65">Reviewing the organisation information and preparing your assessment results.</p>
        </div>
      )}

      <header className="fin-nav">
        <div className="fin-nav-inner">
          <Brand />
          <div className="flex items-center gap-3 sm:gap-5">
            <button type="button" onClick={() => setShowTermsModal(true)} className="text-sm font-semibold text-secondary hover:text-primary transition-colors">Terms</button>
            {user && (
              <div className="hidden sm:flex items-center gap-2.5">
                <span className="h-9 w-9 rounded-xl grid place-items-center text-white text-xs font-bold bg-brand-secondary">{(user.name || user.username || '?')[0].toUpperCase()}</span>
                <span className="leading-tight"><strong className="block text-xs text-primary">{user.name || user.username}</strong><small className="text-[10px] uppercase tracking-wider text-muted">{user.role}</small></span>
              </div>
            )}
            {onLogout && <button type="button" onClick={onLogout} className="action-secondary px-4 min-h-10 text-xs">Sign out</button>}
          </div>
        </div>
      </header>

      <TermsModal isOpen={showTermsModal} onClose={() => setShowTermsModal(false)} onReset={handleTermsReset} />

      <main className="fin-page">
        <div className="onboarding-grid">
          <aside className="journey-panel" aria-label="Assessment progress">
            <span className="eyebrow">Assessment setup</span>
            <h1>Start a new assessment.</h1>
            <p>Choose the organisation information FinComply should include in this review.</p>

            <div className="journey-steps">
              <div className="journey-step complete">
                <span className="journey-step-number"><HiOutlineCheckCircle aria-hidden="true" /></span>
                <div><strong>Terms accepted</strong><span>Your authority to begin this assessment is confirmed.</span></div>
              </div>
              <div className="journey-step active">
                <span className="journey-step-number">2</span>
                <div><strong>Define assessment scope</strong><span>Use your current workspace or provide updated information.</span></div>
              </div>
              <div className="journey-step">
                <span className="journey-step-number">3</span>
                <div><strong>Review results</strong><span>Prioritise findings, assign actions and download the report.</span></div>
              </div>
            </div>

            <div className="journey-note">
              <HiOutlineLockClosed className="text-xl flex-shrink-0" aria-hidden="true" />
              <span>Your account can access only organisation workspaces assigned to you.</span>
            </div>
          </aside>

          <section className="workspace-surface" aria-labelledby="data-source-title">
            <div className="workspace-header">
              <span className="section-eyebrow">Step 2 of 3 · Assessment scope</span>
              <h2 id="data-source-title">Create a new assessment</h2>
              <p>Choose whether to use the organisation’s current workspace or update it before starting.</p>
            </div>

            <div className="workspace-body">
              <div className="mode-grid" role="tablist" aria-label="Assessment data source">
                <button type="button" role="tab" aria-selected={mode === 'existing'} onClick={() => { setMode('existing'); setError(null); }} className={`mode-option ${mode === 'existing' ? 'active' : ''}`}>
                  <span className="mode-icon"><HiOutlineCircleStack className="text-xl" aria-hidden="true" /></span>
                  <span><strong>Use existing workspace</strong><span>Start with the organisation information currently available in FinComply.</span></span>
                </button>
                <button type="button" role="tab" aria-selected={mode === 'upload'} onClick={() => { setMode('upload'); setError(null); }} className={`mode-option ${mode === 'upload' ? 'active' : ''}`}>
                  <span className="mode-icon"><HiOutlineCloudArrowUp className="text-xl" aria-hidden="true" /></span>
                  <span><strong>Update organisation data</strong><span>Provide a complete approved data package before starting the assessment.</span></span>
                </button>
              </div>

              {error && <div className="fin-error mt-4" role="alert">{error}</div>}

              <AnimatePresence mode="wait">
                {mode === 'existing' ? (
                  <motion.div key="existing" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="assessment-panel">
                    <div className="assessment-panel-inner">
                      <div className="flex items-start justify-between gap-4 mb-5">
                        <div><span className="section-eyebrow">Current workspace</span><h3 className="mt-2 text-lg font-semibold text-primary">Use existing organisation information</h3><p className="mt-1 text-xs leading-5 text-secondary">No files are required for this option.</p></div>
                        <span className="h-11 w-11 rounded-2xl grid place-items-center text-white bg-brand-secondary flex-shrink-0"><HiOutlineCircleStack aria-hidden="true" /></span>
                      </div>

                      <label className="fin-label" htmlFor="existing-tenant-id"><span>Organisation ID</span><small>Required</small></label>
                      <input id="existing-tenant-id" className="fin-input font-mono" value={existingTenantId} onChange={(event) => setExistingTenantId(event.target.value.toUpperCase())} placeholder="For example: QUICKLOAN-001" onKeyDown={(event) => { if (event.key === 'Enter') handleRunExisting(); }} />

                      <div className="plain-note mt-4">
                        <HiOutlineArrowPath className="text-lg flex-shrink-0" aria-hidden="true" />
                        <span><strong className="text-primary">Recommended for repeat reviews:</strong> use this option when your organisation information has not changed. If policies, systems or operational records changed, update the workspace first.</span>
                      </div>

                      <div className="process-row">
                        <div className="process-item"><strong>Assessment scope</strong><span>Use the organisation’s current approved information.</span></div>
                        <HiOutlineArrowRight className="process-arrow" aria-hidden="true" />
                        <div className="process-item"><strong>Readiness review</strong><span>Review coverage against selected DPDP obligations.</span></div>
                        <HiOutlineArrowRight className="process-arrow" aria-hidden="true" />
                        <div className="process-item"><strong>Results and actions</strong><span>Receive prioritised findings and recommended actions.</span></div>
                      </div>

                      <button type="button" disabled={!isExistingReady || loading} onClick={handleRunExisting} className="action-primary w-full inline-flex items-center justify-center gap-2">
                        Start assessment <HiOutlineArrowRight aria-hidden="true" />
                      </button>
                    </div>
                  </motion.div>
                ) : (
                  <motion.div key="upload" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="assessment-panel">
                    <div className="assessment-panel-inner">
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-5">
                        <div><span className="section-eyebrow">Workspace update</span><h3 className="mt-2 text-lg font-semibold text-primary">Provide the latest organisation data</h3><p className="mt-1 text-xs leading-5 text-secondary">Upload the complete set of approved files required for this assessment.</p></div>
                        <span className="text-xs font-semibold text-primary whitespace-nowrap">{fileCount} of {FILE_TYPES.length} ready</span>
                      </div>

                      <div className="field-grid mb-5">
                        <div>
                          <label className="fin-label" htmlFor="organisation-name"><span>Organisation name</span><small>Required</small></label>
                          <input id="organisation-name" className="fin-input" value={orgName} onChange={(event) => setOrgName(event.target.value)} placeholder="For example: QuickLoan Finance" />
                        </div>
                        <div>
                          <label className="fin-label" htmlFor="upload-tenant-id"><span>Organisation ID</span><small>Must match every file</small></label>
                          <input id="upload-tenant-id" className="fin-input font-mono" value={tenantId} onChange={(event) => setTenantId(event.target.value.toUpperCase())} placeholder="For example: QUICKLOAN-001" />
                        </div>
                      </div>

                      <div className="plain-note mb-5">
                        <HiOutlineShieldCheck className="text-lg flex-shrink-0" aria-hidden="true" />
                        <span>Each file is checked before the workspace is updated. If required information is missing or inconsistent, the update stops and the existing workspace remains unchanged.</span>
                      </div>

                      <div className="file-grid">
                        {FILE_TYPES.map((type) => <FileZone key={type.id} type={type} file={files[type.id]} onDrop={handleDrop} onRemove={handleRemove} />)}
                      </div>

                      <div className="mt-5 flex items-center justify-between gap-4 text-xs text-secondary">
                        <span><strong className="text-primary">{fileCount}</strong> files selected</span>
                        <span>{fileCount === FILE_TYPES.length ? 'Dataset complete' : `${FILE_TYPES.length - fileCount} remaining`}</span>
                      </div>
                      <div className="file-progress-track mt-2" aria-label={`${fileCount} of ${FILE_TYPES.length} files selected`}>
                        <motion.div className="file-progress-bar" animate={{ width: `${(fileCount / FILE_TYPES.length) * 100}%` }} />
                      </div>

                      <button type="button" disabled={!isUploadReady || loading} onClick={handleRunUpload} className="action-primary w-full mt-5 inline-flex items-center justify-center gap-2">
                        Update workspace and start assessment <HiOutlineArrowRight aria-hidden="true" />
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </section>
        </div>

        <footer className="mt-8 flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-muted">
          <span>FinComply · Decision-support system · DPDP Act 2023</span>
          <span>Terms version {TERMS_VERSION}</span>
        </footer>
      </main>
    </motion.div>
  );
}
