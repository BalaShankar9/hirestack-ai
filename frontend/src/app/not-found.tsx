"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Home } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary via-violet-600 to-indigo-700 px-4 relative overflow-hidden">
      {/* Background decoration */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute -right-20 -top-20 h-[400px] w-[400px] rounded-full border-[50px] border-white/5" />
        <div className="absolute -bottom-20 -left-20 h-[300px] w-[300px] rounded-full border-[40px] border-white/5" />
        <div className="absolute left-1/3 top-1/4 h-[200px] w-[200px] rounded-full bg-white/5 blur-3xl" />
      </div>
      <motion.div
        className="relative z-10 flex flex-col items-center text-center"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <motion.span
          className="text-[10rem] font-extrabold leading-none tracking-tighter text-white/20 select-none sm:text-[14rem]"
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          404
        </motion.span>

        <h1 className="mt-2 text-3xl font-bold text-white sm:text-4xl">
          Page not found
        </h1>

        <p className="mt-3 max-w-md text-base text-white/70">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>

        <Button asChild size="lg" variant="secondary" className="mt-8">
          <Link href="/">
            <Home className="mr-2 h-4 w-4" />
            Go back home
          </Link>
        </Button>
      </motion.div>
    </div>
  );
}
