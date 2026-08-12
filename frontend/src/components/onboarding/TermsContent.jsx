/**
 * TermsContent
 * ============
 * The full System Use Terms text, rendered as numbered sections.
 * Shared between TermsGate (inline) and TermsModal (read-only review).
 *
 * Content accurately reflects the current Fin-Comply system behavior:
 *   - deterministic weighted-signal compliance engine
 *   - HMAC-SHA256 pseudonymization (NOT anonymization)
 *   - 16 DPDP rules + 3 internal policy rules
 *   - XGBoost supplementary risk prediction
 *   - SHAP feature attribution
 *   - Gemini-assisted narration with PII boundary scanner
 *   - deterministic fallback explanations
 */
export default function TermsContent() {
  return (
    <div className="space-y-6 text-sm leading-relaxed text-secondary">
      {/* Section 1 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">1. Purpose of Fin-Comply</h4>
        <p className="mb-2">
          Fin-Comply is a compliance decision-support system designed to assist organisations in assessing
          selected obligations under India&apos;s Digital Personal Data Protection Act, 2023 and configured
          internal policies.
        </p>
        <p className="mb-2">
          The platform analyses submitted organisational datasets, identifies potential compliance risks,
          calculates risk indicators, and generates explainable findings and remediation guidance.
        </p>
        <p>
          Fin-Comply is a decision-support tool. It is not legal advice, a statutory certification,
          or a guarantee of regulatory compliance.
        </p>
      </section>

      {/* Section 2 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">2. Data You Provide</h4>
        <p className="mb-2">
          A compliance assessment requires organisational information through ten CSV datasets covering:
        </p>
        <ul className="list-disc list-inside space-y-1 ml-2 text-secondary/90">
          <li>governance configuration</li>
          <li>customer records</li>
          <li>consent records</li>
          <li>transaction events</li>
          <li>access logs</li>
          <li>data lifecycle information</li>
          <li>security events</li>
          <li>data-subject requests</li>
          <li>system inventory</li>
          <li>internal policies</li>
        </ul>
        <p className="mt-2">
          The user must ensure that they are authorised to submit the organisation&apos;s data for analysis.
        </p>
        <p className="mt-1">
          Users should not upload unrelated files or information that is unnecessary for the assessment.
        </p>
      </section>

      {/* Section 3 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">3. Data Processing and Pseudonymization</h4>
        <p className="mb-2">
          During ingestion, uploaded CSV files are temporarily processed by the backend.
        </p>
        <p className="mb-2">
          Supported identifying fields are pseudonymized using tenant-scoped HMAC-SHA256 identifiers so
          that required relationships between records can be preserved without relying on the original
          identifier during compliance analysis.
        </p>
        <p className="mb-2">
          Sanitized operational records required by the compliance engine may be stored in PostgreSQL
          for analysis.
        </p>
        <p className="mb-2">
          Compliance evaluation results may also be stored for reporting purposes.
        </p>
        <p>
          Temporary raw CSV copies created during the upload process are removed by the backend after
          the ingestion attempt completes.
        </p>
      </section>

      {/* Section 4 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">4. Automated Compliance Analysis</h4>
        <p className="mb-2">
          The current compliance knowledge base contains 16 DPDP compliance rules and 3 internal
          policy rules.
        </p>
        <p className="mb-2">
          The core compliance engine performs deterministic weighted signal evaluation. Rules identify
          relevant records, evaluate configured evidence signals, calculate rule scores, and classify
          findings such as pass, warning, or violation based on configured thresholds.
        </p>
        <p>
          The compliance determination is made by the deterministic rule engine, not by a generative
          AI model.
        </p>
      </section>

      {/* Section 5 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">5. Machine Learning and Explainability</h4>
        <p className="mb-2">
          Fin-Comply may use an XGBoost model to provide an additional predicted risk tier using
          engineered compliance features derived from assessment findings.
        </p>
        <p className="mb-2">
          Explainability techniques such as SHAP may be used to show which features influenced a
          machine-learning prediction.
        </p>
        <p>
          Machine-learning predictions are supplementary analytical indicators and should not be
          represented as legal determinations.
        </p>
      </section>

      {/* Section 6 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">6. AI-Assisted Explanations</h4>
        <p className="mb-2">
          Fin-Comply may use generative AI services such as Gemini to assist with grounded
          explanations and remediation narratives.
        </p>
        <p className="mb-2">
          The current violation narration flow provides the model with controlled regulatory
          information such as the rule, relevant legal section, legal obligation, and fired
          evidence-signal descriptions.
        </p>
        <p className="mb-2">
          The system contains a PII boundary scanner designed to block the narration request when
          specified personal-data patterns are detected.
        </p>
        <p className="mb-2">
          If AI narration is unavailable or blocked, deterministic fallback explanations may be used.
        </p>
        <p>
          AI-generated explanations may contain errors and must not be treated as professional legal advice.
        </p>
      </section>

      {/* Section 7 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">7. User Responsibilities</h4>
        <p className="mb-2">By using the system, the user confirms that:</p>
        <ul className="list-disc list-inside space-y-1 ml-2 text-secondary/90">
          <li>they are authorised to submit the organisation&apos;s data;</li>
          <li>submitted information is appropriate for compliance assessment;</li>
          <li>they will review generated findings before relying on them;</li>
          <li>
            compliance decisions requiring professional or legal judgement will be independently
            reviewed;
          </li>
          <li>
            they will not attempt to misuse the service, bypass access controls, or submit malicious
            content.
          </li>
        </ul>
      </section>

      {/* Section 8 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">8. Limitations</h4>
        <p className="mb-2">Assessment quality depends on:</p>
        <ul className="list-disc list-inside space-y-1 ml-2 text-secondary/90">
          <li>accuracy of uploaded information;</li>
          <li>completeness of the ten datasets;</li>
          <li>configuration of compliance rules;</li>
          <li>availability of required backend services;</li>
          <li>current implementation of the regulatory knowledge base.</li>
        </ul>
        <p className="mt-2">
          A low risk score or compliant assessment does not constitute formal regulatory certification.
        </p>
        <p className="mt-1">
          References to standards, frameworks, or regulations within the interface must not be
          interpreted as certification by those organisations.
        </p>
      </section>

      {/* Section 9 */}
      <section>
        <h4 className="text-h3 text-primary mb-2">9. Acceptance</h4>
        <p>
          By selecting <em className="text-primary">&ldquo;I have read and agree to the System Use Terms&rdquo;</em>,
          the user acknowledges that they understand the purpose and limitations of Fin-Comply and agrees
          to use the platform in accordance with these terms.
        </p>
      </section>
    </div>
  );
}
