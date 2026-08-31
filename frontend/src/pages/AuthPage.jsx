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
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-semibold uppercase tracking-widest text-secondary">
        {label}
      </label>
      <div className="relative">
        {Icon && (
          <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
            <Icon className="w-4 h-4" />
          </span>
        )}
        <input
          id={id}
          type={showToggle ? (showPassword ? 'text' : 'password') : type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete={autoComplete}
          className={`w-full rounded-xl border bg-surface text-primary text-sm placeholder:text-muted transition-all duration-200
            py-3 pr-4 outline-none
            ${Icon ? 'pl-10' : 'pl-4'}
            ${error
              ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500/20'
              : 'border-subtle focus:border-brand-primary focus:ring-2 focus:ring-blue-500/15'
            }`}
        />
        {showToggle && (
          <button
            type="button"
            onClick={onToggle}
            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted hover:text-secondary transition-colors"
            tabIndex={-1}
          >
            {showPassword ? <HiOutlineEyeSlash className="w-4 h-4" /> : <HiOutlineEye className="w-4 h-4" />}
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
  const colors = ['', 'bg-red-400', 'bg-yellow-400', 'bg-blue-400', 'bg-green-500'];
  const textColors = ['', 'text-red-500', 'text-yellow-600', 'text-blue-600', 'text-green-600'];

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
        className="mt-1 w-full py-3 rounded-xl btn-gradient text-white font-semibold text-sm
          flex items-center justify-center gap-2 shadow-md hover:shadow-lg hover:opacity-90
          transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
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

function RegisterForm({ onSuccess, switchToLogin }) {
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
      <div className="p-3 rounded-xl bg-blue-50/50 border border-blue-100">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-blue-500 mb-3">Your Details</p>
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
      <div className="p-3 rounded-xl bg-indigo-50/50 border border-indigo-100">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-indigo-500 mb-3">Your Company</p>
        <div className="flex flex-col gap-4">
          <InputField
            id="tenantName"
            label="Company Name"
            value={form.tenantName}
            onChange={set('tenantName')}
            placeholder="e.g. HDFC Bank"
            icon={HiOutlineIdentification}
            error={errors.tenantName}
          />
          <div className="flex flex-col gap-1.5">
            <InputField
              id="tenantId"
              label="Company Tenant ID"
              value={form.tenantId}
              onChange={(e) => setForm(f => ({ ...f, tenantId: e.target.value.toUpperCase() }))}
              placeholder="e.g. HDFC-001"
              icon={HiOutlineUser}
              error={errors.tenantId}
            />
            <p className="text-[11px] text-slate-400 pl-0.5">
              Unique identifier for your organisation — letters, numbers, hyphens only. This links your account to your company's data.
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
        className="mt-1 w-full py-3 rounded-xl btn-gradient text-white font-semibold text-sm
          flex items-center justify-center gap-2 shadow-md hover:shadow-lg hover:opacity-90
          transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
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
  { icon: '🛡️', text: 'DPDP Act 2023 compliance engine' },
  { icon: '🤖', text: 'AI-powered rule evaluation' },
  { icon: '📊', text: 'Real-time risk scoring & reporting' },
  { icon: '🔐', text: 'Role-based access control (RBAC)' },
];

export default function AuthPage({ onLoginSuccess }) {
  const [mode, setMode] = useState('landing'); // 'landing' | 'login' | 'register'

  return (
    <div className="min-h-screen bg-base flex">
      {/* ── Left panel: branding ── */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-700 flex-col justify-between p-12">
        {/* Background decoration */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-white/5 blur-3xl" />
          <div className="absolute top-1/2 -left-32 w-80 h-80 rounded-full bg-white/5 blur-3xl" />
          <div className="absolute -bottom-32 right-1/4 w-64 h-64 rounded-full bg-white/5 blur-3xl" />
          {/* Grid pattern */}
          <div className="absolute inset-0 opacity-10" style={{
            backgroundImage: 'linear-gradient(rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.3) 1px, transparent 1px)',
            backgroundSize: '40px 40px'
          }} />
        </div>

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-16">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
              <HiOutlineShieldCheck className="w-6 h-6 text-white" />
            </div>
            <span className="text-white font-bold text-xl tracking-tight">Fin-Comply</span>
          </div>

          <h1 className="text-4xl font-bold text-white leading-tight mb-4">
            India's DPDP<br />Compliance Platform
          </h1>
          <p className="text-blue-100 text-base leading-relaxed mb-10 max-w-sm">
            Automated compliance evaluation against the Digital Personal Data Protection Act 2023. Built for financial institutions.
          </p>

          <div className="flex flex-col gap-4">
            {FEATURES.map((f) => (
              <div key={f.text} className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-white/15 flex items-center justify-center text-base flex-shrink-0">
                  {f.icon}
                </div>
                <span className="text-sm text-blue-50 font-medium">{f.text}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10">
          <p className="text-xs text-blue-200/70">
            © 2024 Fin-Comply. Regulatory Intelligence Engine v2.0
          </p>
        </div>
      </div>

      {/* ── Right panel: auth form ── */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">

          {/* Mobile logo */}
          <div className="flex lg:hidden items-center gap-2 mb-8 justify-center">
            <div className="w-9 h-9 rounded-xl btn-gradient flex items-center justify-center">
              <HiOutlineShieldCheck className="w-5 h-5 text-white" />
            </div>
            <span className="font-bold text-lg text-primary tracking-tight">Fin-Comply</span>
          </div>

          <AnimatePresence mode="wait">
            {/* ── Landing: choose action ── */}
            {mode === 'landing' && (
              <motion.div
                key="landing"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.3 }}
              >
                <div className="text-center mb-10">
                  <div className="inline-flex items-center gap-1.5 bg-blue-50 border border-blue-200 text-blue-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-4">
                    <HiOutlineSparkles className="w-3.5 h-3.5" />
                    DPDP Compliance Engine
                  </div>
                  <h2 className="text-3xl font-bold text-primary mb-2 tracking-tight">Welcome back</h2>
                  <p className="text-secondary text-sm">Sign in to your account or create a new one to get started.</p>
                </div>

                <div className="flex flex-col gap-3">
                  <motion.button
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    onClick={() => setMode('login')}
                    className="w-full py-4 rounded-2xl btn-gradient text-white font-semibold text-base
                      flex items-center justify-center gap-3 shadow-lg hover:shadow-xl
                      hover:opacity-95 transition-all duration-200"
                  >
                    <HiOutlineLockClosed className="w-5 h-5" />
                    Sign In
                    <HiOutlineArrowRight className="w-5 h-5 ml-auto" />
                  </motion.button>

                  <motion.button
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    onClick={() => setMode('register')}
                    className="w-full py-4 rounded-2xl bg-surface border-2 border-subtle text-primary font-semibold text-base
                      flex items-center justify-center gap-3 hover:border-brand-primary/40 hover:bg-elevated
                      transition-all duration-200 shadow-card"
                  >
                    <HiOutlineIdentification className="w-5 h-5 text-brand-primary" />
                    Create Account
                    <HiOutlineArrowRight className="w-5 h-5 ml-auto text-secondary" />
                  </motion.button>
                </div>

                <div className="mt-8 grid grid-cols-2 gap-3">
                  {FEATURES.map((f) => (
                    <div key={f.text} className="flex items-start gap-2 p-3 rounded-xl bg-elevated">
                      <span className="text-sm">{f.icon}</span>
                      <span className="text-xs text-secondary leading-tight">{f.text}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {/* ── Login form ── */}
            {mode === 'login' && (
              <motion.div
                key="login"
                initial={{ opacity: 0, x: 30 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -30 }}
                transition={{ duration: 0.25 }}
              >
                <button
                  onClick={() => setMode('landing')}
                  className="flex items-center gap-1.5 text-sm text-secondary hover:text-primary mb-8 transition-colors group"
                >
                  <svg className="w-4 h-4 rotate-180 group-hover:-translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                  Back
                </button>

                <div className="mb-8">
                  <div className="w-12 h-12 rounded-2xl btn-gradient flex items-center justify-center mb-4 shadow-md">
                    <HiOutlineLockClosed className="w-6 h-6 text-white" />
                  </div>
                  <h2 className="text-2xl font-bold text-primary tracking-tight">Sign in</h2>
                  <p className="text-secondary text-sm mt-1">Enter your credentials to access your account.</p>
                </div>

                <LoginForm
                  onSuccess={onLoginSuccess}
                  switchToRegister={() => setMode('register')}
                />
              </motion.div>
            )}

            {/* ── Register form ── */}
            {mode === 'register' && (
              <motion.div
                key="register"
                initial={{ opacity: 0, x: 30 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -30 }}
                transition={{ duration: 0.25 }}
              >
                <button
                  onClick={() => setMode('landing')}
                  className="flex items-center gap-1.5 text-sm text-secondary hover:text-primary mb-8 transition-colors group"
                >
                  <svg className="w-4 h-4 rotate-180 group-hover:-translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                  Back
                </button>

                <div className="mb-6">
                  <div className="w-12 h-12 rounded-2xl btn-gradient flex items-center justify-center mb-4 shadow-md">
                    <HiOutlineIdentification className="w-6 h-6 text-white" />
                  </div>
                  <h2 className="text-2xl font-bold text-primary tracking-tight">Create account</h2>
                  <p className="text-secondary text-sm mt-1">Fill in your details to get started with Fin-Comply.</p>
                </div>

                <RegisterForm
                  onSuccess={() => {}}
                  switchToLogin={() => setMode('login')}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
