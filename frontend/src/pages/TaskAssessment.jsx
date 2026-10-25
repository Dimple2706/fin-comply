
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  HiOutlineArrowLeft,
  HiOutlineClipboardDocumentCheck,
  HiOutlineExclamationTriangle,
  HiOutlineUserGroup,
} from 'react-icons/hi2';
import {
  getTaskAssignments,
  downloadTaskAssignmentPdf,
} from '../services/api';

const priorityStyles = {
  Critical: 'text-red-600 bg-red-500/10 border-red-500/30',
  High: 'text-orange-600 bg-orange-500/10 border-orange-500/30',
  Medium: 'text-yellow-600 bg-yellow-500/10 border-yellow-500/30',
  Low: 'text-green-600 bg-green-500/10 border-green-500/30',
};

export default function TaskAssessment({ data, onBack }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [pdfError, setPdfError] = useState('');

  const tenantId = data?.tenant_id;
  const auditRunId = data?.audit_run_id;

  useEffect(() => {
    if (!tenantId || !auditRunId) {
      setError('Tenant or audit run information is missing.');
      setLoading(false);
      return;
    }

    let active = true;

    const loadTasks = async () => {
      setLoading(true);
      setError('');

      try {
        const result = await getTaskAssignments(
          tenantId,
          auditRunId
        );

        if (active) {
          setTasks(result.tasks || []);
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Unable to load tasks.');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadTasks();

    return () => {
      active = false;
    };
  }, [tenantId, auditRunId]);

const handleDownloadPdf = async () => {
  setDownloadingPdf(true);
  setPdfError('');

  try {
    const blob = await downloadTaskAssignmentPdf(
      tenantId,
      auditRunId
    );

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = `FinComply_TaskAssignment_${auditRunId}.pdf`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  } catch (err) {
    setPdfError(
      err.message || 'Unable to download Task Assignment PDF.'
    );
  } finally {
    setDownloadingPdf(false);
  }
};

  const criticalCount = tasks.filter(
    (task) => task.priority === 'Critical'
  ).length;

  const highCount = tasks.filter(
    (task) => task.priority === 'High'
  ).length;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="min-h-screen bg-base"
    >
      <nav className="sticky top-0 z-40 bg-surface/90 backdrop-blur-md border-b border-subtle px-6 py-4">
        <div className="container-center flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-2 rounded-md text-secondary hover:text-primary hover:bg-elevated"
              aria-label="Back to dashboard"
            >
              <HiOutlineArrowLeft className="text-xl" />
            </button>

            <div>
              <h1 className="text-xl font-bold text-primary">
                Task Assessment
              </h1>
              <p className="text-sm text-secondary">
                Fin-Comply Remediation Assignments
              </p>
            </div>
          </div>

          <span className="hidden sm:block text-sm text-secondary">
            Tenant: {tenantId}
          </span>
        </div>
      </nav>

      <main className="container-center py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-primary">
            Compliance Task Assignments
          </h2>
          <p className="mt-2 text-secondary">
            Actionable remediation tasks generated from
            confirmed compliance violations.
          </p>

          <div className="mt-5 flex flex-col items-start gap-3">
          <button
          type="button"
             onClick={handleDownloadPdf}
             disabled={downloadingPdf || loading || !!error}
         className="px-5 py-3 rounded-lg font-semibold text-white btn-gradient shadow-glow hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
         {downloadingPdf
                  ? 'Generating PDF...'
          : 'Download Task Assignment Report'}
         </button>

         {pdfError && (
         <p role="alert" className="text-sm text-red-600">
           {pdfError}
         </p>
         )}
        </div>

        </div>

        {loading ? (
          <div className="py-20 text-center text-secondary">
            Loading task assignments...
          </div>
        ) : error ? (
          <div
            role="alert"
            className="rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-red-600"
          >
            {error}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
              {[
                {
                  label: 'Total Tasks',
                  value: tasks.length,
                  icon: HiOutlineClipboardDocumentCheck,
                },
                {
                  label: 'Critical Priority',
                  value: criticalCount,
                  icon: HiOutlineExclamationTriangle,
                },
                {
                  label: 'High Priority',
                  value: highCount,
                  icon: HiOutlineUserGroup,
                },
              ].map(({ label, value, icon: Icon }) => (
                <div
                  key={label}
                  className="bg-surface border border-subtle rounded-xl p-5"
                >
                  <Icon className="text-2xl text-brand-primary mb-3" />
                  <p className="text-sm text-secondary">
                    {label}
                  </p>
                  <p className="text-3xl font-bold text-primary mt-1">
                    {value}
                  </p>
                </div>
              ))}
            </div>

            {tasks.length === 0 ? (
              <div className="bg-surface border border-subtle rounded-xl p-10 text-center">
                <HiOutlineClipboardDocumentCheck className="text-4xl text-secondary mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-primary">
                  No task assignments found
                </h3>
                <p className="text-secondary mt-2">
                  No actionable task evidence is available
                  for this audit run.
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {tasks.map((task) => (
                  <div
                    key={`${task.rule_id}-${task.signal_id}`}
                    className="bg-surface border border-subtle rounded-xl p-6"
                  >
                    <div className="flex flex-wrap justify-between gap-3 mb-4">
                      <div>
                        <p className="text-xs font-semibold text-brand-primary mb-2">
                          {task.rule_id} / {task.signal_id}
                        </p>

                        <h3 className="text-lg font-bold text-primary">
                          {task.task_title}
                        </h3>
                      </div>

                      <span
                        className={`self-start px-3 py-1 rounded-full text-xs font-semibold border ${
                          priorityStyles[task.priority] ||
                          priorityStyles.Medium
                        }`}
                      >
                        {task.priority}
                      </span>
                    </div>

                    <p className="text-sm text-secondary mb-5">
                      {task.task_description}
                    </p>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
                      <div>
                        <p className="text-xs text-muted mb-1">
                          Responsible Team
                        </p>
                        <p className="font-semibold text-primary">
                          {task.responsible_team}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-muted mb-1">
                          Affected Records
                        </p>
                        <p className="font-semibold text-primary">
                          {task.affected_records_count}
                        </p>
                      </div>
                    </div>

                    <div className="border-t border-subtle pt-4">
                      <h4 className="font-semibold text-primary mb-3">
                        Recommended Remediation Steps
                      </h4>

                      <ol className="list-decimal pl-5 space-y-2 text-sm text-secondary">
                        {(task.remediation_steps || []).map(
                          (step, index) => (
                            <li key={index}>
                              {typeof step === 'string'
                                ? step
                                : JSON.stringify(step)}
                            </li>
                          )
                        )}
                      </ol>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </motion.div>
  );
}
