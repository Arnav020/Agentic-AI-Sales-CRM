import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { LogIn, UserPlus, BarChart3, Mail, Lock, User, ArrowRight, AlertCircle, CheckCircle, Shield } from "lucide-react";
import axios from "axios";

export default function Auth() {
  const location = useLocation();
  const [isLogin, setIsLogin] = useState(location.state?.mode === "signup" ? false : true);
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const navigate = useNavigate();

  const BASE_URL = "http://127.0.0.1:8000";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    try {
      if (isLogin) {
        const res = await axios.post(`${BASE_URL}/auth/login`, {
          username: form.username,
          password: form.password,
        });

        // ✅ Explicitly store username separately
        localStorage.setItem("username", form.username);

        // (Optional) store full response if needed later
        localStorage.setItem("user", JSON.stringify(res.data));

        setMessage("✅ Login successful! Redirecting...");
        setTimeout(() => navigate("/dashboard"), 1000);
      }
      else {
        // SIGN UP
        await axios.post(`${BASE_URL}/auth/signup`, {
          username: form.username,
          email: form.email,
          password: form.password,
        });

        setMessage("🎉 Signup successful! Please login.");
        setIsLogin(true);
        setForm({ username: "", email: "", password: "" });
      }
    } catch (err) {
      setMessage(err.response?.data?.detail || "❌ Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 relative overflow-hidden">
      {/* Animated Background Elements - Blue themed only */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 -left-20 w-96 h-96 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse"></div>
        <div className="absolute top-40 -right-20 w-96 h-96 bg-indigo-200 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse" style={{ animationDelay: "1s" }}></div>
        <div className="absolute -bottom-20 left-1/2 w-96 h-96 bg-blue-300 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse" style={{ animationDelay: "2s" }}></div>
      </div>

      <div className="relative z-10 w-full max-w-md mx-4">
        {/* Main Card */}
        <div className="bg-white shadow-2xl rounded-2xl p-8 border border-gray-100 transition-all duration-500">
          {/* Logo Section */}
          <Link to="/" className="flex justify-center items-center mb-10 space-x-2 group">
            <div className="bg-indigo-600 p-2.5 rounded-lg shadow-md group-hover:bg-indigo-700 transition-colors">
              <BarChart3 className="w-6 h-6 text-white" />
            </div>
            <span className="text-2xl font-bold text-indigo-600">
              Agentic CRM
            </span>
          </Link>

          {/* Header */}
          <div className="text-center mb-8">
            <h2 className="text-3xl font-bold text-gray-900 mb-2">
              {isLogin ? "Welcome Back" : "Create Account"}
            </h2>
            <p className="text-gray-600 text-sm">
              {isLogin
                ? "Sign in to continue to your dashboard"
                : "Join Agentic CRM and automate your sales"}
            </p>
          </div>

          {/* Alert Message */}
          {message && (
            <div className={`mb-6 p-3.5 rounded-lg flex items-center space-x-3 ${
              message.startsWith("✅") || message.startsWith("🎉")
                ? "bg-green-50 border border-green-200"
                : "bg-red-50 border border-red-200"
            }`}>
              {message.startsWith("✅") || message.startsWith("🎉") ? (
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
              ) : (
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
              )}
              <p className={`text-sm font-medium ${
                message.startsWith("✅") || message.startsWith("🎉")
                  ? "text-green-800"
                  : "text-red-800"
              }`}>
                {message.replace(/^[✅🎉❌]\s*/, "")}
              </p>
            </div>
          )}

          {/* Form */}
          <form className="space-y-5" onSubmit={handleSubmit}>
            {/* Username Field */}
            <div className="group">
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Username
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <User className="w-5 h-5 text-gray-400 group-focus-within:text-indigo-600 transition-colors" />
                </div>
                <input
                  type="text"
                  placeholder="Enter your username"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  required
                  className="w-full pl-11 pr-4 py-3 border border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all"
                />
              </div>
            </div>

            {/* Email Field (Signup Only) */}
            {!isLogin && (
              <div className="group">
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Email Address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                    <Mail className="w-5 h-5 text-gray-400 group-focus-within:text-indigo-600 transition-colors" />
                  </div>
                  <input
                    type="email"
                    placeholder="you@example.com"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    required
                    className="w-full pl-11 pr-4 py-3 border border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all"
                  />
                </div>
              </div>
            )}

            {/* Password Field */}
            <div className="group">
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <Lock className="w-5 h-5 text-gray-400 group-focus-within:text-indigo-600 transition-colors" />
                </div>
                <input
                  type="password"
                  placeholder="Enter your password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  required
                  className="w-full pl-11 pr-4 py-3 border border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all"
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full bg-indigo-600 hover:bg-indigo-700 text-white py-3.5 rounded-lg font-semibold transition-all shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2 mt-6"
            >
              {loading ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  <span>Processing...</span>
                </>
              ) : (
                <>
                  {isLogin ? (
                    <LogIn className="w-5 h-5" />
                  ) : (
                    <UserPlus className="w-5 h-5" />
                  )}
                  <span>{isLogin ? "Sign In" : "Create Account"}</span>
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="relative my-7">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200"></div>
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="px-3 bg-white text-gray-500 font-medium">or</span>
            </div>
          </div>

          {/* Toggle Between Login/Signup */}
          <div className="text-center">
            <p className="text-sm text-gray-600">
              {isLogin ? (
                <>
                  Don't have an account?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setIsLogin(false);
                      setMessage("");
                      setForm({ username: "", email: "", password: "" });
                    }}
                    className="font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
                  >
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setIsLogin(true);
                      setMessage("");
                      setForm({ username: "", email: "", password: "" });
                    }}
                    className="font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>
          </div>
        </div>

        {/* Bottom Links */}
        <div className="mt-6 flex items-center justify-between text-sm">
          <Link
            to="/"
            className="inline-flex items-center space-x-1.5 text-gray-600 hover:text-indigo-600 transition-colors group"
          >
            <ArrowRight className="w-4 h-4 rotate-180 group-hover:-translate-x-1 transition-transform" />
            <span>Back to Home</span>
          </Link>
          
          <div className="flex items-center space-x-1.5 text-gray-500">
            <Shield className="w-4 h-4" />
            <span>Secure & Encrypted</span>
          </div>
        </div>
      </div>
    </div>
  );
}