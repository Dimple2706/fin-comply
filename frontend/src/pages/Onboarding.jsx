import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useDropzone } from 'react-dropzone';
import { 
  HiOutlineShieldCheck, 
  HiOutlineUsers, 
  HiOutlineClipboardDocumentCheck, 
  HiOutlineArrowsRightLeft, 
  HiOutlineKey, 
  HiOutlineClock, 
  HiOutlineLockClosed, 
  HiOutlineDocumentText, 
  HiOutlineServer, 
  HiOutlineScale,
  HiOutlineCloudArrowUp,
  HiOutlineCheckCircle,
  HiOutlineXMark
} from 'react-icons/hi2';
import Card from '../components/ui/Card';
import { runAnalysis } from '../services/api';
import { getTermsAcceptance, clearTermsAcceptance } from '../utils/termsAcceptance';
import { TERMS_VERSION } from '../utils/termsAcceptance';
import TermsGate from '../components/onboarding/TermsGate';
import OnboardingProgress from '../components/onboarding/OnboardingProgress';
import TermsModal from '../components/onboarding/TermsModal';

const FILE_TYPES = [
  { id: 'governance_config', label: 'Governance Config', icon: HiOutlineShieldCheck },
  { id: 'customer_master', label: 'Customer Master', icon: HiOutlineUsers },
  { id: 'consent_records', label: 'Consent Records', icon: HiOutlineClipboardDocumentCheck },
  { id: 'transaction_events', label: 'Transaction Events', icon: HiOutlineArrowsRightLeft },
  { id: 'access_logs', label: 'Access Logs', icon: HiOutlineKey },
  { id: 'data_lifecycle', label: 'Data Lifecycle', icon: HiOutlineClock },
  { id: 'security_events', label: 'Security Events', icon: HiOutlineLockClosed },
  { id: 'dsar_requests', label: 'DSAR Requests', icon: HiOutlineDocumentText },
  { id: 'system_inventory', label: 'System Inventory', icon: HiOutlineServer },
  { id: 'policies', label: 'Policies', icon: HiOutlineScale },
];

function FileZone({ type, file, onDrop, onRemove }) {
  const Icon = type.icon;
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted) => onDrop(type.id, accepted[0]),
    accept: { 'text/csv': ['.csv'] },
    maxFiles: 1
  });

  if (file) {
    return (
      <motion.div 
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="h-[88px] rounded-xl border border-low bg-green-500/5 px-4 flex items-center justify-between"
      >
        <div className="flex items-center gap-3 overflow-hidden">
          <HiOutlineCheckCircle className="text-low text-xl flex-shrink-0" />
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium text-primary truncate max-w-[150px]">
              {file.name}
            </span>
            <span className="text-caption">{type.label}</span>
          </div>
        </div>
        <button 
          onClick={() => onRemove(type.id)}
          className="p-1.5 hover:bg-black/20 rounded-md text-secondary hover:text-primary transition-colors"
        >
          <HiOutlineXMark />
        </button>
      </motion.div>
    );
  }

  return (
    <div 
      {...getRootProps()} 
      className={`h-[88px] rounded-xl border border-dashed transition-all cursor-pointer flex items-center justify-between px-4
        ${isDragActive ? 'border-brand-primary bg-brand-glow' : 'border-subtle bg-surface hover:border-brand-primary/50 hover:bg-elevated'}`}
    >
      <input {...getInputProps()} />
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg bg-elevated flex items-center justify-center text-secondary border border-subtle">
          <Icon className="text-xl" />
        </div>
        <span className="text-sm font-medium text-secondary">{type.label}</span>
      </div>
      <HiOutlineCloudArrowUp className="text-secondary text-xl" />
    </div>
  );
}

export default function Onboarding({ onComplete }) {
  // Terms acceptance — initialized from localStorage
  const [termsAccepted, setTermsAccepted] = useState(() => getTermsAcceptance());
  const [showTermsModal, setShowTermsModal] = useState(false);

  // Upload form state
  const [orgName, setOrgName] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [files, setFiles] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleTermsAccepted = useCallback(() => {
    setTermsAccepted(true);
  }, []);

  const handleTermsReset = useCallback(() => {
    clearTermsAcceptance();
    setTermsAccepted(false);
  }, []);

  const handleDrop = useCallback((typeId, file) => {
    setFiles(prev => ({ ...prev, [typeId]: file }));
  }, []);

  const handleRemove = useCallback((typeId) => {
    setFiles(prev => {
      const copy = { ...prev };
      delete copy[typeId];
      return copy;
    });
  }, []);

  const fileCount = Object.keys(files).length;
  const isReady = fileCount === 10 && orgName.trim() && tenantId.trim();

  const handleRun = async () => {
    if (!isReady) return;
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('tenant_name', orgName);
    formData.append('tenant_id', tenantId);
    
    for (const [key, file] of Object.entries(files)) {
      formData.append(key, file);
    }

    try {
      const result = await runAnalysis(formData);
      onComplete(result);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  // ─── STEP 1: Terms Gate ───────────────────────────────────────────────
  // The upload interface is NOT rendered (not merely hidden) until accepted.
  if (!termsAccepted) {
    return (
      <AnimatePresence mode="wait">
        <TermsGate onAccept={handleTermsAccepted} />
      </AnimatePresence>
    );
  }

  // ─── STEP 2: Organisation Setup + Data Upload ─────────────────────────
  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen relative"
    >
      {/* Full page overlay while loading */}
      {loading && (
        <div className="fixed inset-0 z-50 bg-base/80 backdrop-blur-sm flex flex-col items-center justify-center">
          <div className="h-12 w-12 rounded-full border-4 border-brand-primary/20 border-t-brand-primary animate-spin mb-4" />
          <h3 className="text-h2 text-primary">Evaluating DPDP and policy compliance rules...</h3>
          <p className="text-secondary mt-2">Evaluating compliance signals and generating explainable risk insights.</p>
        </div>
      )}

      {/* Top Nav */}
      <nav className="h-16 flex items-center justify-between px-6 border-b border-subtle bg-base/50 backdrop-blur-md sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="font-bold text-lg tracking-tight">Fin-Comply</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-elevated text-secondary border border-subtle">
            v{TERMS_VERSION}
          </span>
        </div>
        <button
          onClick={() => setShowTermsModal(true)}
          className="text-sm text-secondary hover:text-primary transition-colors"
        >
          Review Terms
        </button>
      </nav>

      {/* Terms Review Modal */}
      <TermsModal
        isOpen={showTermsModal}
        onClose={() => setShowTermsModal(false)}
        onReset={handleTermsReset}
      />

      <main className="container-center pb-24">
        {/* Hero Section */}
        <div className="pt-16 sm:pt-20 max-w-[720px] mx-auto text-center">
          <motion.div 
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ staggerChildren: 0.1 }}
            className="flex flex-wrap justify-center gap-2 mb-6"
          >
            {['DPDP Act 2023', 'Risk Prediction', 'SHAP XAI', 'Explainable AI'].map(pill => (
              <span key={pill} className="px-3 py-1 rounded-full text-xs font-medium border border-subtle bg-elevated/50 text-secondary">
                {pill}
              </span>
            ))}
          </motion.div>

          <motion.h1 
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="text-display mb-6"
          >
            AI-Powered <span className="text-gradient">DPDP Compliance</span><br />
            Intelligence
          </motion.h1>

          <motion.p 
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="text-body text-secondary max-w-[560px] mx-auto mb-6"
          >
            Run a complete compliance assessment using deterministic rule evaluation and explainable risk prediction. Powered by weighted signal scoring and SHAP feature attribution.
          </motion.p>

          {/* Progress indicator */}
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.55 }}
            className="mb-4"
          >
            <OnboardingProgress currentStep={2} />
          </motion.div>

          <motion.div 
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.6 }}
            className="flex justify-center items-center gap-4 text-sm font-medium text-muted"
          >
            <span className="flex items-center gap-1.5"><HiOutlineCheckCircle className="text-low" /> 16 DPDP Rules</span>
            <span className="w-1 h-1 rounded-full bg-subtle" />
            <span className="flex items-center gap-1.5"><HiOutlineCheckCircle className="text-low" /> 3 Policy Rules</span>
            <span className="w-1 h-1 rounded-full bg-subtle" />
            <span className="flex items-center gap-1.5"><HiOutlineCheckCircle className="text-low" /> PDF Reports</span>
          </motion.div>
        </div>

        {/* Form Card */}
        <motion.div 
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.7 }}
          className="mt-12 max-w-[880px] mx-auto"
        >
          <Card className="overflow-hidden">
            <div className="p-8 pb-6 border-b border-subtle bg-base/30">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-label text-secondary mb-2">Organisation Name</label>
                  <input 
                    type="text" 
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    placeholder="e.g. Acme Corp"
                    className="w-full h-11 px-4 rounded-lg bg-elevated border border-subtle text-primary placeholder-muted focus:outline-none focus:border-brand-primary focus:ring-1 focus:ring-brand-primary transition-all"
                  />
                </div>
                <div>
                  <label className="block text-label text-secondary mb-2">Tenant Identifier</label>
                  <input 
                    type="text" 
                    value={tenantId}
                    onChange={(e) => setTenantId(e.target.value)}
                    placeholder="tenant_001"
                    className="w-full h-11 px-4 rounded-lg bg-elevated border border-subtle text-primary placeholder-muted font-mono focus:outline-none focus:border-brand-primary focus:ring-1 focus:ring-brand-primary transition-all"
                  />
                </div>
              </div>
            </div>

            <div className="p-8">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h3 className="text-h3 text-primary">Upload Data Files</h3>
                  <p className="text-caption mt-1">Provide CSV extracts for the 10 core systems.</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-secondary">
                    <strong className={fileCount === 10 ? 'text-low' : 'text-primary'}>{fileCount}</strong> / 10 files
                  </span>
                </div>
              </div>

              {error && (
                <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {error}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {FILE_TYPES.map(type => (
                  <FileZone 
                    key={type.id} 
                    type={type} 
                    file={files[type.id]} 
                    onDrop={handleDrop} 
                    onRemove={handleRemove}
                  />
                ))}
              </div>
            </div>

            {/* Progress Bar */}
            <div className="h-1 w-full bg-elevated relative overflow-hidden">
              <motion.div 
                className="absolute inset-y-0 left-0 bg-gradient-to-r from-brand-primary to-brand-secondary"
                initial={{ width: 0 }}
                animate={{ width: `${(fileCount / 10) * 100}%` }}
                transition={{ ease: "easeOut" }}
              />
            </div>

            <div className="p-6 bg-base/30">
              <button
                disabled={!isReady || loading}
                onClick={handleRun}
                className={`w-full h-14 rounded-lg font-medium text-white transition-all flex items-center justify-center gap-2
                  ${isReady && !loading ? 'btn-gradient shadow-glow hover:opacity-90' : 'bg-elevated text-muted cursor-not-allowed border border-subtle'}`}
              >
                {loading ? 'Processing...' : 'Run Compliance Analysis'}
              </button>
            </div>
          </Card>
        </motion.div>

        <footer className="mt-16 text-center text-caption text-muted">
          Fin-Comply v{TERMS_VERSION} • Decision-Support System • DPDP Act 2023
        </footer>
      </main>
    </motion.div>
  );
}
