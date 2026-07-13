import { useState } from 'react';
import { motion } from 'framer-motion';
import { HiOutlineArrowLeft, HiOutlineDocumentArrowDown, HiOutlineCodeBracketSquare } from 'react-icons/hi2';
import ExecutiveSummary from '../components/dashboard/ExecutiveSummary';
import MetricsSection from '../components/dashboard/MetricsSection';
import ChartsSection from '../components/dashboard/ChartsSection';
import RemediationSection from '../components/dashboard/RemediationSection';
import ViolationsSection from '../components/dashboard/ViolationsSection';
import { downloadPdfReport } from '../services/api';

export default function Dashboard({ data, onReset }) {
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  if (!data) return null;

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fin-comply-${data.tenant_id}-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    try {
      const blob = await downloadPdfReport(data.tenant_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `FinComply_AuditReport_${data.tenant_id}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err.message || 'Failed to generate PDF.');
    } finally {
      setDownloadingPdf(false);
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen bg-base"
    >
      {/* Sticky Top Nav */}
      <nav className="sticky top-0 z-40 h-16 bg-surface/80 backdrop-blur-md border-b border-subtle px-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button 
            onClick={onReset}
            className="p-2 text-secondary hover:text-primary hover:bg-elevated rounded-md transition-colors"
            title="Back to Upload"
          >
            <HiOutlineArrowLeft className="text-xl" />
          </button>
          <div className="flex items-center gap-2 border-l border-subtle pl-4">
            <span className="font-bold text-lg tracking-tight">Fin-Comply</span>
            <span className="text-caption text-secondary mt-0.5">Compliance Report</span>
          </div>
        </div>

        <div className="hidden md:flex flex-col items-center">
          <span className="text-sm font-medium text-primary">Report for {data.tenant_id}</span>
        </div>

        <div className="flex items-center gap-3">
          <button 
            onClick={onReset}
            className="hidden sm:block px-4 py-1.5 text-sm font-medium text-secondary hover:text-primary border border-subtle rounded-md hover:bg-elevated transition-colors"
          >
            New Analysis
          </button>
          <button 
            onClick={handleDownloadPdf}
            disabled={downloadingPdf}
            className={`px-4 py-1.5 text-sm font-medium text-white rounded-md transition-all flex items-center gap-2
              ${downloadingPdf 
                ? 'bg-elevated text-muted cursor-not-allowed' 
                : 'btn-gradient shadow-glow hover:opacity-90'}`}
          >
            {downloadingPdf ? (
              <span className="h-4 w-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
            ) : (
              <HiOutlineDocumentArrowDown className="text-lg" />
            )}
            <span className="hidden sm:inline">{downloadingPdf ? 'Generating...' : 'Download PDF'}</span>
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <main className="container-center py-8">
        <ExecutiveSummary summary={data.executive_summary} tenantId={data.tenant_id} />
        
        <MetricsSection data={data} />
        
        <ChartsSection 
          breakdown={data.agent_breakdown} 
          contributions={data.risk_contributions} 
          violations={data.violations} 
        />
        
        <RemediationSection items={data.remediation_priority} />
        
        <ViolationsSection violations={data.violations} />

        {/* SECTION 6: DOWNLOAD BUTTONS */}
        <motion.section 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="mt-16 mb-12 flex flex-col items-center"
        >
          <div className="flex flex-col sm:flex-row gap-4 mb-4">
            <button 
              onClick={handleDownloadPdf}
              disabled={downloadingPdf}
              className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-medium text-white btn-gradient shadow-glow hover:opacity-90 transition-all min-w-[220px]"
            >
              <HiOutlineDocumentArrowDown className="text-xl" />
              {downloadingPdf ? 'Generating PDF...' : 'Download PDF Report'}
            </button>
            <button 
              onClick={handleDownloadJson}
              className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-medium text-brand-primary border border-brand-primary/50 hover:bg-brand-primary/10 transition-colors min-w-[220px]"
            >
              <HiOutlineCodeBracketSquare className="text-xl" />
              Export JSON
            </button>
          </div>
          <div className="text-center text-caption text-muted">
            <p className="font-mono mb-1">Report ID: {data.tenant_id}-{Date.now().toString().slice(-6)}</p>
            <p>Generated: {new Date().toLocaleString('en-GB')}</p>
          </div>
        </motion.section>
      </main>
    </motion.div>
  );
}
