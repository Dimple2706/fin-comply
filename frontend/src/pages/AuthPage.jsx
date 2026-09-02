import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  HiOutlineShieldCheck,
  HiOutlineUser,
  HiOutlineLockClosed,
  HiOutlineEnvelope,
  HiOutlineIdentification,
  HiOutlineEye,
  HiOutlineEyeSlash,
  HiOutlineArrowRight,
  HiOutlineCheckCircle,
  HiOutlineExclamationCircle,
  HiOutlineSparkles,
} from 'react-icons/hi2';
import { loginUser, registerUser } from '../services/api';

/* ─── Tiny helpers ────────────────────────────────────────────────────────── */

function InputField({ id, label, type = 'text', value, onChange, placeholder, icon: Icon, error, showToggle, onToggle, showPassword, autoComplete = 'off' }) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-[13px] font-semibold text-primary">
        {label}
      </label>
      <div className="relative">
        {Icon && (
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
            <Icon className="w-5 h-5" />
          </span>
        )}
        <input
          id={id}
          type={showToggle ? (showPassword ? 'text' : 'password') : type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete={autoComplete}
          className={`auth-input ${Icon ? '' : '!pl-4'} ${error ? 'has-error' : ''}`}
        />
        {showToggle && (
          <button
            type="button"
            onClick={onToggle}
            className="absolute right-3.5 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-primary transition-colors"
            tabIndex={-1}
          >
            {showPassword ? <HiOutlineEyeSlash className="w-5 h-5" /> : <HiOutlineEye className="w-5 h-5" />}
          </button>
        )}
      </div>
      <AnimatePresence>
        {error && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="text-xs text-red-500 flex items-center gap-1.5 mt-0.5"
          >
            <HiOutlineExclamationCircle className="w-3.5 h-3.5 flex-shrink-0" />
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

function PasswordStrength({ password }) {
  if (!password) return null;
  const checks = [
    password.length >= 8,
    /[a-z]/.test(password) && /[A-Z]/.test(password),
    /[0-9]/.test(password),
    /[^A-Za-z0-9]/.test(password),
  ];
  const score = checks.filter(Boolean).length;
  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
  const colors = ['', 'bg-red-400', 'bg-yellow-500', 'bg-[#bf6a45]', 'bg-[#23665e]'];
  const textColors = ['', 'text-red-500', 'text-yellow-700', 'text-[#a85635]', 'text-[#23665e]'];

  return (
    <div className="mt-1">
      <div className="flex gap-1 mb-1">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-all duration-300 ${i <= score ? colors[score] : 'bg-elevated'}`}
          />
        ))}
      </div>
      {score > 0 && (
        <p className={`text-xs font-medium ${textColors[score]}`}>{labels[score]} password</p>
      )}
    </div>
  );
}

/* ─── Login Form ─────────────────────────────────────────────────────────── */

function LoginForm({ onSuccess, switchToRegister }) {
  const [form, setForm] = useState({ username: '', password: '' });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [globalError, setGlobalError] = useState('');
  const [showPw, setShowPw] = useState(false);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const validate = () => {
    const errs = {};
    if (!form.username.trim()) errs.username = 'Username is required';
    if (!form.password) errs.password = 'Password is required';
    return errs;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setGlobalError('');
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setLoading(true);
    try {
      const data = await loginUser(form.username.trim(), form.password);
      onSuccess(data);
    } catch (err) {
      setGlobalError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <InputField
        id="username"
        label="Username"
        value={form.username}
        onChange={set('username')}
        placeholder="your_username"
        icon={HiOutlineUser}
        error={errors.username}
        autoComplete="username"
      />
      <InputField
        id="password"
        label="Password"
        value={form.password}
        onChange={set('password')}
        placeholder="••••••••"
        icon={HiOutlineLockClosed}
        error={errors.password}
        showToggle
        showPassword={showPw}
        onToggle={() => setShowPw((v) => !v)}
        autoComplete="current-password"
      />

      <AnimatePresence>
        {globalError && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="flex items-start gap-2.5 bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700"
          >
            <HiOutlineExclamationCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{globalError}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        type="submit"
        disabled={loading}
        className="action-primary mt-1 w-full px-5 flex items-center justify-center gap-2 disabled:opacity-60"
      >
        {loading ? (
          <span className="flex items-center gap-2">
            <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Signing in…
          </span>
        ) : (
          <>Sign In <HiOutlineArrowRight className="w-4 h-4" /></>
        )}
      </button>

      <p className="text-center text-sm text-secondary">
        Don't have an account?{' '}
        <button
          type="button"
          onClick={switchToRegister}
          className="text-brand-primary font-semibold hover:underline"
        >
          Create one
        </button>
      </p>
    </form>
  );
}

/* ─── Register Form ──────────────────────────────────────────────────────── */

function RegisterForm({ switchToLogin }) {
  const [form, setForm] = useState({ name: '', email: '', username: '', password: '', confirm: '', tenantName: '', tenantId: '' });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [globalError, setGlobalError] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [done, setDone] = useState(false);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const validate = () => {
    const errs = {};
    if (form.name.trim().length < 2) errs.name = 'At least 2 characters';
    else if (form.name.trim().length > 128) errs.name = 'Max 128 characters';
    if (!form.email.trim()) errs.email = 'Email is required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = 'Invalid email address';
    else if (form.email.trim().length > 254) errs.email = 'Max 254 characters';
    if (!form.username.trim()) errs.username = 'Username is required';
    else if (form.username.length < 3) errs.username = 'At least 3 characters';
    else if (form.username.length > 64) errs.username = 'Max 64 characters';
    else if (!/^[a-zA-Z0-9_-]+$/.test(form.username)) errs.username = 'Letters, numbers, _ and - only';
    if (!form.password) errs.password = 'Password is required';
    else if (form.password.length < 8) errs.password = 'At least 8 characters';
    else if (new TextEncoder().encode(form.password).length > 72) errs.password = 'Max 72 UTF-8 bytes';
    else if (!/[a-z]/.test(form.password)) errs.password = 'Add a lowercase letter';
    else if (!/[A-Z]/.test(form.password)) errs.password = 'Add an uppercase letter';
    else if (!/[0-9]/.test(form.password)) errs.password = 'Add a number';
    else if (!/[^A-Za-z0-9]/.test(form.password)) errs.password = 'Add a special character';
    if (!form.confirm) errs.confirm = 'Please confirm your password';
    else if (form.confirm !== form.password) errs.confirm = 'Passwords do not match';
    if (form.tenantName.trim().length < 2) errs.tenantName = 'At least 2 characters';
    else if (form.tenantName.trim().length > 128) errs.tenantName = 'Max 128 characters';
    if (!form.tenantId.trim()) errs.tenantId = 'Tenant ID is required';
    else if (!/^[a-zA-Z0-9_-]+$/.test(form.tenantId.trim())) errs.tenantId = 'Letters, numbers, - and _ only (e.g. HDFC-001)';
    else if (form.tenantId.trim().length > 64) errs.tenantId = 'Max 64 characters';
    return errs;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setGlobalError('');
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setLoading(true);
    try {
      await registerUser({
        name: form.name.trim(),
        email: form.email.trim().toLowerCase(),
        username: form.username.trim(),
        password: form.password,
        tenant_id: form.tenantId.trim().toUpperCase(),
        tenant_name: form.tenantName.trim(),
      });
      setDone(true);
    } catch (err) {
      setGlobalError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex flex-col items-center gap-4 py-6 text-center"
      >
        <div className="w-16 h-16 rounded-full bg-green-50 border-2 border-green-200 flex items-center justify-center">
          <HiOutlineCheckCircle className="w-8 h-8 text-green-500" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-primary">Account created!</h3>
          <p className="text-sm text-secondary mt-1">You can now sign in with your credentials.</p>
        </div>
        <button
          onClick={switchToLogin}
          className="mt-2 px-6 py-2.5 rounded-xl btn-gradient text-white font-semibold text-sm
            flex items-center gap-2 shadow-md hover:opacity-90 transition-all duration-200"
        >
          Go to Sign In <HiOutlineArrowRight className="w-4 h-4" />
        </button>
      </motion.div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* ── Personal Details ── */}
      <div className="auth-form-section">
        <p className="section-eyebrow mb-4">Your details</p>
        <div className="flex flex-col gap-4">
          <InputField id="name" label="Full Name" value={form.name} onChange={set('name')} placeholder="Jane Smith" icon={HiOutlineIdentification} error={errors.name} />
          <InputField id="email" label="Email Address" type="email" value={form.email} onChange={set('email')} placeholder="jane@company.com" icon={HiOutlineEnvelope} error={errors.email} autoComplete="email" />
          <InputField id="reg-username" label="Username" value={form.username} onChange={set('username')} placeholder="jane_smith" icon={HiOutlineUser} error={errors.username} autoComplete="username" />
          <div className="flex flex-col gap-1.5">
            <InputField
              id="reg-password"
              label="Password"
              value={form.password}
              onChange={set('password')}
              placeholder="At least 8 characters"
              icon={HiOutlineLockClosed}
              error={errors.password}
              showToggle
              showPassword={showPw}
              onToggle={() => setShowPw((v) => !v)}
              autoComplete="new-password"
            />
            <PasswordStrength password={form.password} />
          </div>
          <InputField
            id="confirm"
            label="Confirm Password"
            value={form.confirm}
            onChange={set('confirm')}
            placeholder="Re-enter password"
            icon={HiOutlineLockClosed}
            error={errors.confirm}
            showToggle
            showPassword={showPw}
            onToggle={() => setShowPw((v) => !v)}
            autoComplete="new-password"
          />
        </div>
      </div>

      {/* ── Company Details ── */}
      <div className="auth-form-section">
        <p className="section-eyebrow mb-4">Your organisation</p>
        <div className="flex flex-col gap-4">
          <InputField
            id="tenantName"
            label="Organisation name"
            value={form.tenantName}
            onChange={set('tenantName')}
            placeholder="e.g. HDFC Bank"
            icon={HiOutlineIdentification}
            error={errors.tenantName}
          />
          <div className="flex flex-col gap-1.5">
            <InputField
              id="tenantId"
              label="Organisation ID"
              value={form.tenantId}
              onChange={(e) => setForm(f => ({ ...f, tenantId: e.target.value.toUpperCase() }))}
              placeholder="e.g. HDFC-001"
              icon={HiOutlineUser}
              error={errors.tenantId}
            />
            <p className="text-xs leading-5 text-muted pl-0.5">
              Use a unique code such as QUICKLOAN-001. An existing organisation ID cannot be claimed during registration.
            </p>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {globalError && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="flex items-start gap-2.5 bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700"
          >
            <HiOutlineExclamationCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{globalError}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        type="submit"
        disabled={loading}
        className="action-primary mt-1 w-full px-5 flex items-center justify-center gap-2 disabled:opacity-60"
      >
        {loading ? (
          <span className="flex items-center gap-2">
            <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Creating account…
          </span>
        ) : (
          <>Create Account <HiOutlineArrowRight className="w-4 h-4" /></>
        )}
      </button>

      <p className="text-center text-sm text-secondary">
        Already have an account?{' '}
        <button
          type="button"
          onClick={switchToLogin}
          className="text-brand-primary font-semibold hover:underline"
        >
          Sign in
        </button>
      </p>
    </form>
  );
}

/* ─── Auth Page (main export) ────────────────────────────────────────────── */

const FEATURES = [
  { icon: HiOutlineShieldCheck, title: 'DPDP readiness', description: 'Review selected obligations in one organised workspace.' },
  { icon: HiOutlineCheckCircle, title: 'Prioritised findings', description: 'Focus first on the gaps that require attention.' },
  { icon: HiOutlineSparkles, title: 'Clear risk insights', description: 'Understand the factors influencing each assessment.' },
  { icon: HiOutlineLockClosed, title: 'Controlled access', description: 'Keep each organisation workspace limited to authorised users.' },
];

function AuthBrand() {
  return (
    <div className="flex items-center gap-3">
      <span className="h-11 w-11 rounded-2xl grid place-items-center bg-[#dabf9f] text-[#2b202e] shadow-lg">
        <HiOutlineShieldCheck className="h-6 w-6" aria-hidden="true" />
      </span>
      <span className="leading-tight">
        <strong className="block text-lg text-[#fffaf3]">FinComply</strong>
        <small className="mt-1 block text-[10px] font-bold uppercase tracking-[0.15em] text-[#fffaf3]/55">DPDP readiness workspace</small>
      </span>
    </div>
  );
}

function BackButton({ onClick }) {
  return (
    <button type="button" onClick={onClick} className="mb-7 inline-flex min-h-10 items-center gap-2 rounded-xl px-2 text-sm font-semibold text-secondary hover:text-primary transition-colors">
      <HiOutlineArrowRight className="h-4 w-4 rotate-180" aria-hidden="true" />
      Back
    </button>
  );
}

export default function AuthPage({ onLoginSuccess }) {
  const [mode, setMode] = useState('landing');

  return (
    <div className="auth-shell">
      <section className="auth-story" aria-labelledby="product-heading">
        <div className="auth-story-inner">
          <AuthBrand />

          <div className="auth-story-copy">
            <span className="eyebrow">Privacy compliance, made actionable</span>
            <h1 id="product-heading">Turn privacy obligations into clear action.</h1>
            <p>
              Review your organisation’s DPDP readiness, prioritise gaps and prepare an evidence-led assessment for professional review.
            </p>

            <div className="auth-feature-grid">
              {FEATURES.map(({ icon: Icon, title, description }) => (
                <article className="auth-feature" key={title}>
                  <span className="auth-feature-icon"><Icon className="h-5 w-5" aria-hidden="true" /></span>
                  <span><strong>{title}</strong><span>{description}</span></span>
                </article>
              ))}
            </div>
          </div>

          <p className="auth-story-footer">Decision support for organisations preparing for India’s DPDP Act, 2023.</p>
        </div>
      </section>

      <section className="auth-panel" aria-label="Account access">
        <div className="auth-card">
          <AnimatePresence mode="wait">
            {mode === 'landing' && (
              <motion.div key="landing" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.25 }}>
                <div className="auth-heading">
                  <span className="section-eyebrow">Secure workspace access</span>
                  <h2>Welcome to FinComply</h2>
                  <p>Sign in to continue an assessment, or create an account for a new organisation workspace.</p>
                </div>

                <div className="grid gap-3">
                  <motion.button type="button" whileTap={{ scale: 0.99 }} onClick={() => setMode('login')} className="auth-choice primary">
                    <span className="auth-choice-icon"><HiOutlineLockClosed className="h-5 w-5" aria-hidden="true" /></span>
                    <span><strong>Sign in</strong><small>Continue to your authorised workspace</small></span>
                    <HiOutlineArrowRight className="h-5 w-5" aria-hidden="true" />
                  </motion.button>
                  <motion.button type="button" whileTap={{ scale: 0.99 }} onClick={() => setMode('register')} className="auth-choice">
                    <span className="auth-choice-icon"><HiOutlineIdentification className="h-5 w-5" aria-hidden="true" /></span>
                    <span><strong>Create an account</strong><small>Set up a new organisation workspace</small></span>
                    <HiOutlineArrowRight className="h-5 w-5 text-secondary" aria-hidden="true" />
                  </motion.button>
                </div>

                <p className="mt-6 text-center text-xs leading-5 text-muted">Access is limited to organisation workspaces assigned to your account.</p>
              </motion.div>
            )}

            {mode === 'login' && (
              <motion.div key="login" initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.22 }}>
                <BackButton onClick={() => setMode('landing')} />
                <div className="auth-heading">
                  <span className="section-eyebrow">Account access</span>
                  <h2>Welcome back</h2>
                  <p>Enter your username and password to continue to your workspace.</p>
                </div>
                <LoginForm onSuccess={onLoginSuccess} switchToRegister={() => setMode('register')} />
              </motion.div>
            )}

            {mode === 'register' && (
              <motion.div key="register" initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.22 }}>
                <BackButton onClick={() => setMode('landing')} />
                <div className="auth-heading">
                  <span className="section-eyebrow">New workspace</span>
                  <h2>Create an account</h2>
                  <p>Set up an account for a new organisation. Existing organisation access must be granted by its administrator.</p>
                </div>
                <RegisterForm switchToLogin={() => setMode('login')} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </section>
    </div>
  );
}
