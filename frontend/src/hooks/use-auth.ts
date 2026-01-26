"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  sendPasswordResetEmail,
  updatePassword as firebaseUpdatePassword,
  GoogleAuthProvider,
  GithubAuthProvider,
  signInWithPopup,
  updateProfile,
} from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useAuth as useAuthContext } from "@/components/providers";

export function useAuth() {
  const { user, loading } = useAuthContext();
  const router = useRouter();

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await signInWithEmailAndPassword(auth, email, password);
    return result;
  }, []);

  const signUp = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const result = await createUserWithEmailAndPassword(auth, email, password);
      if (fullName && result.user) {
        await updateProfile(result.user, { displayName: fullName });
      }
      return result;
    },
    []
  );

  const signOut = useCallback(async () => {
    await firebaseSignOut(auth);
    router.push("/login");
  }, [router]);

  const signInWithGoogle = useCallback(async () => {
    const provider = new GoogleAuthProvider();
    const result = await signInWithPopup(auth, provider);
    return result;
  }, []);

  const signInWithGithub = useCallback(async () => {
    const provider = new GithubAuthProvider();
    const result = await signInWithPopup(auth, provider);
    return result;
  }, []);

  const resetPassword = useCallback(async (email: string) => {
    await sendPasswordResetEmail(auth, email);
  }, []);

  const updatePassword = useCallback(async (newPassword: string) => {
    if (auth.currentUser) {
      await firebaseUpdatePassword(auth.currentUser, newPassword);
    }
  }, []);

  return {
    user,
    loading,
    signIn,
    signUp,
    signOut,
    signInWithGoogle,
    signInWithGithub,
    resetPassword,
    updatePassword,
    isAuthenticated: !!user,
  };
}
