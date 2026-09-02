const TERM_SECTIONS = [
  {
    title: '1. What FinComply does',
    paragraphs: [
      'FinComply helps organisations review their readiness for selected requirements under India’s Digital Personal Data Protection Act, 2023 and their own internal policies.',
      'It highlights possible gaps, provides a risk summary and suggests actions for review. It is a decision-support tool, not legal advice or an official compliance certificate.',
    ],
  },
  {
    title: '2. Information used for an assessment',
    paragraphs: [
      'An assessment uses ten CSV files containing information about governance, customers, consent, transactions, access, data retention, security incidents, data-subject requests, systems and policies.',
      'Only information needed for the assessment should be uploaded. The person uploading the files must be authorised by the organisation to do so.',
    ],
  },
  {
    title: '3. How uploaded information is handled',
    paragraphs: [
      'FinComply applies safeguards while organisational information is uploaded, reviewed and stored. Access is limited to authorised organisation workspaces.',
      'Approved records and assessment results may be stored in the organisation’s workspace. Temporary upload copies are removed after the upload attempt finishes.',
    ],
  },
  {
    title: '4. How results are produced',
    paragraphs: [
      'FinComply reviews the available organisation information against selected regulatory and policy requirements. Results include findings, priorities and suggested next steps.',
      'Some estimates and summaries are automated. They support professional judgement and should not replace it.',
    ],
  },
  {
    title: '5. Your responsibilities',
    bullets: [
      'Make sure you are authorised to upload the organisation’s information.',
      'Provide complete and accurate files in the required format.',
      'Review findings before making legal, operational or customer decisions.',
      'Do not upload unrelated information or try to bypass access controls.',
    ],
  },
  {
    title: '6. Important limitations',
    paragraphs: [
      'Results depend on the quality and completeness of the information provided. Missing or incorrect records can lead to an incomplete assessment.',
      'A low risk score does not guarantee compliance, and a high risk score should be investigated rather than treated as a final legal conclusion.',
    ],
  },
  {
    title: '7. Your acceptance',
    paragraphs: [
      'By accepting these terms, you confirm that you understand the purpose and limits of FinComply and will use it only for an authorised organisational assessment.',
    ],
  },
];

export default function TermsContent() {
  return (
    <div className="space-y-7 text-sm leading-relaxed text-secondary">
      {TERM_SECTIONS.map((section) => (
        <section key={section.title}>
          <h4 className="text-base font-semibold text-primary mb-2">{section.title}</h4>
          {section.paragraphs?.map((paragraph) => (
            <p key={paragraph} className="mb-2 last:mb-0">{paragraph}</p>
          ))}
          {section.bullets && (
            <ul className="list-disc pl-5 space-y-2 text-secondary">
              {section.bullets.map((item) => <li key={item}>{item}</li>)}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
