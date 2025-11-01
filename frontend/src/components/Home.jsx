import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  Users,
  Megaphone,
  TrendingUp,
  Sparkles,
  Workflow,
  PieChart,
  LogIn,
  UserPlus,
  ArrowRight,
  Check,
  Zap,
  Target,
  Shield,
  Clock,
} from "lucide-react";

export default function Home() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <div className="min-h-screen bg-white text-gray-800">
      {/* Navbar */}
      <nav className={`sticky top-0 z-50 transition-all duration-300 ${
        scrolled ? "bg-white/95 backdrop-blur-lg shadow-sm" : "bg-white/80 backdrop-blur-md"
      } border-b border-gray-100`}>
        <div className="max-w-7xl mx-auto flex justify-between items-center px-6 py-4">
          <div className="flex items-center space-x-2">
            <div className="bg-gradient-to-br from-blue-600 to-purple-600 p-2 rounded-lg">
              <BarChart3 className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              Agentic CRM
            </span>
          </div>
          <div className="hidden md:flex space-x-8 text-[15px] font-medium">
            <a href="#features" className="hover:text-blue-600 transition-colors">
              Features
            </a>
            <a href="#how-it-works" className="hover:text-blue-600 transition-colors">
              How It Works
            </a>
            <a href="#action" className="hover:text-blue-600 transition-colors">
              Demo
            </a>
          </div>
          <div className="flex items-center space-x-3">
             {/* Login Button */}
            <Link
              to="/auth"
              state={{ mode: "login" }}
              className="flex items-center text-gray-700 hover:text-blue-600 transition-colors font-medium text-sm px-4 py-2 rounded-lg hover:bg-gray-50"
            >
              <LogIn className="w-4 h-4 mr-1.5" />
              Login
            </Link>

            {/* Sign Up Button */}
            <Link
              to="/auth"
              state={{ mode: "signup" }}
              className="flex items-center bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white px-5 py-2 rounded-lg transition-all font-medium text-sm shadow-lg shadow-blue-500/30 hover:shadow-xl hover:shadow-blue-500/40"
            >
              <UserPlus className="w-4 h-4 mr-1.5" />
              Sign Up Free
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative bg-gradient-to-b from-blue-50 via-purple-50 to-white overflow-hidden">
        {/* Animated background elements */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-20 left-10 w-72 h-72 bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse"></div>
          <div className="absolute top-40 right-10 w-72 h-72 bg-purple-200 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse" style={{ animationDelay: "1s" }}></div>
        </div>

        <div className="relative max-w-7xl mx-auto px-6 py-20 text-center">
          {/* Announcement Badge */}
          <div className="inline-flex items-center space-x-2 bg-white border border-gray-200 rounded-full px-4 py-2 mb-8 shadow-sm">
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 text-white text-xs font-semibold px-2 py-1 rounded-full">NEW</span>
            <span className="text-sm text-gray-600">AI-powered lead scoring is now live</span>
            <ArrowRight className="w-4 h-4 text-gray-400" />
          </div>

          <h1 className="text-5xl md:text-7xl font-bold text-gray-900 mb-6 leading-tight">
            Empower Your Sales with
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent"> AI-Driven </span>
            CRM
          </h1>
          <p className="text-lg md:text-xl text-gray-600 max-w-3xl mx-auto mb-10 leading-relaxed">
            Transform your sales pipeline with intelligent automation, predictive analytics, and seamless enrichment. Focus on closing deals while AI handles the rest.
          </p>
          
          <div className="flex justify-center mb-16">
            <button className="group bg-gradient-to-r from-blue-600 to-purple-600 text-white px-10 py-4 rounded-xl hover:from-blue-700 hover:to-purple-700 transition-all font-semibold text-lg shadow-xl shadow-blue-500/30 hover:shadow-2xl hover:shadow-blue-500/40 hover:-translate-y-0.5 flex items-center">
              Get Started
              <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
            </button>
          </div>

          {/* Interactive Dashboard Preview */}
          <div className="mt-16 relative">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-600 to-purple-600 rounded-3xl blur-3xl opacity-20"></div>
            <div className="relative bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl shadow-2xl overflow-hidden mx-auto max-w-5xl border border-slate-700">
              <div className="h-[450px] relative p-8">
                {/* Browser Chrome */}
                <div className="absolute top-6 left-6 flex space-x-2">
                  <div className="w-3 h-3 bg-red-500 rounded-full"></div>
                  <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
                  <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                </div>
                
                {/* Dashboard Content */}
                <div className="pt-16 grid grid-cols-3 gap-6">
                  {/* Stats Cards */}
                  <div className="col-span-2 space-y-4">
                    <div className="grid grid-cols-3 gap-4">
                      {[
                        { label: "Active Leads", value: "2,847", change: "+12.5%", color: "blue" },
                        { label: "Conversion", value: "34.2%", change: "+5.3%", color: "green" },
                        { label: "Revenue", value: "$89K", change: "+23.1%", color: "purple" },
                      ].map((stat) => (
                        <div key={stat.label} className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-4">
                          <div className={`text-xs text-${stat.color}-400 font-medium mb-2`}>{stat.label}</div>
                          <div className="text-2xl font-bold text-white mb-1">{stat.value}</div>
                          <div className="text-xs text-green-400 font-medium">{stat.change}</div>
                        </div>
                      ))}
                    </div>
                    
                    {/* Chart Area */}
                    <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-6">
                      <div className="flex items-end space-x-3 h-40">
                        {[40, 65, 45, 80, 60, 90, 70, 85].map((height, idx) => (
                          <div key={idx} className="flex-1 bg-gradient-to-t from-blue-500 to-purple-500 rounded-t-lg opacity-80 hover:opacity-100 transition-opacity" style={{ height: `${height}%` }}></div>
                        ))}
                      </div>
                    </div>
                  </div>
                  
                  {/* Activity Feed */}
                  <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-xl p-4">
                    <div className="text-sm font-semibold text-white mb-4">Recent Activity</div>
                    <div className="space-y-3">
                      {[
                        { color: "bg-blue-500", text: "New lead captured" },
                        { color: "bg-green-500", text: "Deal closed" },
                        { color: "bg-purple-500", text: "Email sent" },
                        { color: "bg-orange-500", text: "Task completed" },
                      ].map((activity, idx) => (
                        <div key={idx} className="flex items-center space-x-3">
                          <div className={`w-2 h-2 ${activity.color} rounded-full`}></div>
                          <div className="text-xs text-gray-400">{activity.text}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Social Proof */}
      <section className="py-12 bg-white border-y border-gray-100">
        <div className="max-w-7xl mx-auto px-6">
          <p className="text-center text-gray-500 text-sm mb-8">Trusted by leading sales teams worldwide</p>
          <div className="flex flex-wrap justify-center items-center gap-12 opacity-40">
            {["Company A", "Company B", "Company C", "Company D", "Company E"].map((company) => (
              <div key={company} className="text-2xl font-bold text-gray-400">{company}</div>
            ))}
          </div>
        </div>
      </section>

      {/* 4 Steps Section */}
      <section className="py-24 bg-gradient-to-b from-white to-gray-50" id="how-it-works">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              Automate in 4 Simple Steps
            </h2>
            <p className="text-gray-600 text-lg max-w-2xl mx-auto">
              Get your sales pipeline running on autopilot with our intuitive setup process
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              { icon: <BarChart3 className="w-8 h-8" />, num: "01", title: "Connect Data", desc: "Integrate your tools and import data with a single click.", gradient: "from-blue-500 to-blue-600" },
              { icon: <Users className="w-8 h-8" />, num: "02", title: "Define Agents", desc: "Configure AI agents to enrich, qualify, and automate tasks.", gradient: "from-purple-500 to-purple-600" },
              { icon: <Megaphone className="w-8 h-8" />, num: "03", title: "Launch Campaigns", desc: "Run adaptive AI campaigns with personalized outreach.", gradient: "from-green-500 to-green-600" },
              { icon: <TrendingUp className="w-8 h-8" />, num: "04", title: "Analyze Results", desc: "Track KPIs and get actionable insights instantly.", gradient: "from-orange-500 to-orange-600" },
            ].map((step) => (
              <div key={step.num} className="group relative bg-white rounded-2xl p-8 shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 hover:border-gray-200 hover:-translate-y-2">
                <div className={`absolute top-6 right-6 text-6xl font-bold bg-gradient-to-br ${step.gradient} bg-clip-text text-transparent opacity-10`}>
                  {step.num}
                </div>
                <div className={`bg-gradient-to-br ${step.gradient} w-16 h-16 rounded-xl flex items-center justify-center mb-6 text-white shadow-lg`}>
                  {step.icon}
                </div>
                <h3 className="text-xl font-bold mb-3 text-gray-900">{step.title}</h3>
                <p className="text-gray-600 leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="bg-white py-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              Features Built for Modern Sales Teams
            </h2>
            <p className="text-gray-600 text-lg max-w-2xl mx-auto">
              Empower your team with smart automation, insightful analytics, and adaptive AI
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              { icon: <Sparkles className="w-7 h-7" />, title: "AI-Lead Enrichment", desc: "Automatically enrich lead data with accurate, real-time insights from multiple sources.", gradient: "from-blue-500 to-blue-600", items: ["Contact info", "Company data", "Social profiles"] },
              { icon: <Workflow className="w-7 h-7" />, title: "Autonomous Campaigns", desc: "Set up intelligent, self-learning campaigns with zero manual effort.", gradient: "from-purple-500 to-purple-600", items: ["Smart triggers", "A/B testing", "Auto-optimization"] },
              { icon: <PieChart className="w-7 h-7" />, title: "Predictive Analytics", desc: "Forecast sales trends and improve your decision-making precision.", gradient: "from-green-500 to-green-600", items: ["Deal scoring", "Churn prediction", "Revenue forecast"] },
              { icon: <Zap className="w-7 h-7" />, title: "Instant Automation", desc: "Create workflows in minutes with our no-code builder.", gradient: "from-yellow-500 to-yellow-600", items: ["Drag & drop", "Templates", "Integrations"] },
              { icon: <Target className="w-7 h-7" />, title: "Smart Targeting", desc: "Identify and prioritize your best prospects automatically.", gradient: "from-red-500 to-red-600", items: ["Lead scoring", "Segmentation", "Recommendations"] },
              { icon: <Shield className="w-7 h-7" />, title: "Enterprise Security", desc: "Bank-level security with SOC 2 compliance and encryption.", gradient: "from-indigo-500 to-indigo-600", items: ["Data encryption", "SSO", "Audit logs"] },
            ].map((feature) => (
              <div key={feature.title} className="group bg-gradient-to-b from-gray-50 to-white rounded-2xl p-8 hover:shadow-xl transition-all duration-300 border border-gray-100 hover:border-gray-200">
                <div className={`bg-gradient-to-br ${feature.gradient} w-14 h-14 rounded-xl flex items-center justify-center mb-6 text-white shadow-lg group-hover:scale-110 transition-transform`}>
                  {feature.icon}
                </div>
                <h3 className="text-xl font-bold mb-3 text-gray-900">{feature.title}</h3>
                <p className="text-gray-600 mb-4 leading-relaxed">{feature.desc}</p>
                <ul className="space-y-2">
                  {feature.items.map((item) => (
                    <li key={item} className="flex items-center text-sm text-gray-500">
                      <Check className="w-4 h-4 text-green-500 mr-2 flex-shrink-0" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* See in Action */}
      <section id="action" className="py-24 bg-gradient-to-b from-gray-50 to-white">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20">
            <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              See Agentic CRM in Action
            </h2>
            <p className="text-gray-600 text-lg max-w-2xl mx-auto">
              Discover how AI automates workflows, enriches leads, and optimizes results
            </p>
          </div>

          <div className="space-y-24">
            {/* Analytics Demo */}
            <div className="grid lg:grid-cols-2 gap-16 items-center">
              <div>
                <div className="inline-flex items-center space-x-2 bg-blue-50 text-blue-600 text-sm font-semibold px-4 py-2 rounded-full mb-6">
                  <PieChart className="w-4 h-4" />
                  <span>Analytics</span>
                </div>
                <h3 className="text-3xl md:text-4xl font-bold text-gray-900 mb-6">
                  Real-Time Analytics Dashboard
                </h3>
                <p className="text-gray-600 text-lg leading-relaxed mb-8">
                  Visualize KPIs and performance trends in real-time. Get instant insights that help you adapt campaigns faster and smarter.
                </p>
                <ul className="space-y-3">
                  {["Custom dashboards", "Live data sync", "Exportable reports", "Team collaboration"].map((item) => (
                    <li key={item} className="flex items-center text-gray-700">
                      <Check className="w-5 h-5 text-green-500 mr-3" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="relative">
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-purple-500 rounded-3xl blur-2xl opacity-20"></div>
                <div className="relative bg-gradient-to-br from-blue-50 to-purple-100 rounded-3xl p-8 shadow-2xl">
                  <div className="bg-white rounded-2xl p-8">
                    <div className="flex justify-between items-center mb-8">
                      <h4 className="text-xl font-bold text-gray-900">Analytics Overview</h4>
                      <div className="flex space-x-2">
                        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                        <div className="w-2 h-2 bg-gray-300 rounded-full"></div>
                        <div className="w-2 h-2 bg-gray-300 rounded-full"></div>
                      </div>
                    </div>
                    <div className="flex items-end space-x-3 h-44 mb-8">
                      {[50, 70, 45, 85, 60].map((height, idx) => (
                        <div key={idx} className="bg-gradient-to-t from-blue-400 to-blue-500 rounded-t-lg flex-1 hover:from-blue-500 hover:to-blue-600 transition-all cursor-pointer" style={{ height: `${height}%` }}></div>
                      ))}
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4">
                        <div className="text-sm text-gray-600 mb-1">Conversion Rate</div>
                        <div className="text-3xl font-bold text-blue-600">64%</div>
                      </div>
                      <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4">
                        <div className="text-sm text-gray-600 mb-1">Active Deals</div>
                        <div className="text-3xl font-bold text-purple-600">142</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Workflow Demo */}
            <div className="grid lg:grid-cols-2 gap-16 items-center">
              <div className="relative order-2 lg:order-1">
                <div className="absolute inset-0 bg-gradient-to-br from-orange-500 to-red-500 rounded-3xl blur-2xl opacity-20"></div>
                <div className="relative bg-gradient-to-br from-orange-50 to-red-50 rounded-3xl p-8 shadow-2xl">
                  <div className="bg-white rounded-2xl p-8">
                    <div className="flex items-center justify-between mb-6">
                      <h4 className="text-xl font-bold text-gray-900">Workflow Builder</h4>
                      <Clock className="w-5 h-5 text-gray-400" />
                    </div>
                    <div className="space-y-3">
                      {[
                        ["Start", "bg-gradient-to-r from-orange-400 to-orange-500 text-white"],
                        ["Enrich Data", "bg-gradient-to-r from-orange-500 to-orange-600 text-white"],
                        ["Send Email", "bg-gradient-to-r from-blue-500 to-blue-600 text-white"],
                        ["Wait 2 Days", "bg-gradient-to-r from-gray-300 to-gray-400 text-gray-800"],
                        ["Follow Up", "bg-gradient-to-r from-red-500 to-red-600 text-white"],
                      ].map(([step, cls], idx) => (
                        <div key={idx}>
                          <div className={`${cls} rounded-xl p-4 text-center font-semibold shadow-lg hover:scale-105 transition-transform cursor-pointer`}>
                            {step}
                          </div>
                          {idx < 4 && (
                            <div className="flex justify-center my-2">
                              <ArrowRight className="w-5 h-5 text-gray-400 rotate-90" />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              <div className="order-1 lg:order-2">
                <div className="inline-flex items-center space-x-2 bg-orange-50 text-orange-600 text-sm font-semibold px-4 py-2 rounded-full mb-6">
                  <Workflow className="w-4 h-4" />
                  <span>Automation</span>
                </div>
                <h3 className="text-3xl md:text-4xl font-bold text-gray-900 mb-6">
                  Intuitive Workflow Builder
                </h3>
                <p className="text-gray-600 text-lg leading-relaxed mb-8">
                  Create smart automation sequences visually with our drag-and-drop builder. Connect triggers, actions, and delays to personalize engagement at scale.
                </p>
                <ul className="space-y-3">
                  {["No-code interface", "Pre-built templates", "Conditional logic", "Real-time testing"].map((item) => (
                    <li key={item} className="flex items-center text-gray-700">
                      <Check className="w-5 h-5 text-green-500 mr-3" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-50 border-t border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-12">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center space-x-2 mb-4">
                <div className="bg-gradient-to-br from-blue-600 to-purple-600 p-2 rounded-lg">
                  <BarChart3 className="w-5 h-5 text-white" />
                </div>
                <span className="text-lg font-bold">Agentic CRM</span>
              </div>
              <p className="text-sm text-gray-600">AI-powered sales automation for modern teams</p>
            </div>
            {[
              { title: "Product", links: ["Features", "Pricing", "Security", "Roadmap"] },
              { title: "Company", links: ["About", "Careers", "Blog", "Press"] },
              { title: "Resources", links: ["Documentation", "Help Center", "API", "Community"] },
            ].map((section) => (
              <div key={section.title}>
                <h3 className="font-semibold text-gray-900 mb-4">{section.title}</h3>
                <ul className="space-y-2">
                  {section.links.map((link) => (
                    <li key={link}>
                      <a href="#" className="text-sm text-gray-600 hover:text-blue-600 transition-colors">
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="border-t border-gray-200 pt-8 flex flex-col md:flex-row items-center justify-between">
            <p className="text-sm text-gray-500">
              © {new Date().getFullYear()} Agentic CRM. All rights reserved.
            </p>
            <div className="flex space-x-6 mt-4 md:mt-0">
              <a href="#" className="text-sm text-gray-500 hover:text-gray-800 transition-colors">Privacy</a>
              <a href="#" className="text-sm text-gray-500 hover:text-gray-800 transition-colors">Terms</a>
              <a href="#" className="text-sm text-gray-500 hover:text-gray-800 transition-colors">Contact</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}