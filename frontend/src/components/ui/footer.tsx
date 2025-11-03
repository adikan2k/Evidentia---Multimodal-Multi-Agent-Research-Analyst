import { GlassCard } from "@/components/ui/glass-card";
import { Brain, Github, Twitter, Linkedin, Mail } from "lucide-react";
import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-white/10 backdrop-blur-sm bg-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="md:col-span-2">
            <div className="flex items-center space-x-3 mb-4">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <Brain className="w-5 h-5 text-white" />
              </div>
              <span className="text-xl font-bold text-white">Evidentia</span>
            </div>
            <p className="text-white/70 text-sm mb-4 max-w-md">
              AI-powered research assistant that transforms complex queries into comprehensive, 
              evidence-based reports in seconds.
            </p>
            <p className="text-white/60 italic text-sm">
              "AI-powered research, simplified for everyone."
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-white font-semibold mb-4">Product</h4>
            <ul className="space-y-2">
              <li>
                <Link href="/" className="text-white/70 hover:text-white text-sm transition-colors">
                  Research
                </Link>
              </li>
              <li>
                <Link href="/about" className="text-white/70 hover:text-white text-sm transition-colors">
                  About
                </Link>
              </li>
              <li>
                <Link href="/notes" className="text-white/70 hover:text-white text-sm transition-colors">
                  Notes
                </Link>
              </li>
            </ul>
          </div>

          {/* Creators */}
          <div>
            <h4 className="text-white font-semibold mb-4">Created By</h4>
            <ul className="space-y-2">
              <li>
                <span className="text-white/70 text-sm">Aditya Kanbargi</span>
                <span className="text-white/50 text-xs block">Full-stack & AI Integration</span>
              </li>
              <li>
                <span className="text-white/70 text-sm">Sanjana Kadambe Muralidhar</span>
                <span className="text-white/50 text-xs block">Data Science & ML Research</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="border-t border-white/10 mt-8 pt-8">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <p className="text-white/60 text-sm mb-4 md:mb-0">
              © 2024 Evidentia. Built with passion for research and discovery.
            </p>
            <div className="flex items-center space-x-6">
              <a href="mailto:contact@evidentia.ai" className="text-white/60 hover:text-white transition-colors">
                <Mail className="w-4 h-4" />
              </a>
              <a href="#" className="text-white/60 hover:text-white transition-colors">
                <Github className="w-4 h-4" />
              </a>
              <a href="#" className="text-white/60 hover:text-white transition-colors">
                <Twitter className="w-4 h-4" />
              </a>
              <a href="#" className="text-white/60 hover:text-white transition-colors">
                <Linkedin className="w-4 h-4" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
