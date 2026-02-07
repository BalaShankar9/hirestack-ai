"use client"

import { useCallback, useState } from "react"
import { useDropzone } from "react-dropzone"
import { cn } from "@/lib/utils"
import { Upload, File, X, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"

interface UploadZoneProps {
  onUpload: (file: File) => Promise<void>
  accept?: Record<string, string[]>
  maxSize?: number
  className?: string
}

export function UploadZone({
  onUpload,
  accept = {
    "application/pdf": [".pdf"],
    "application/msword": [".doc"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
      ".docx",
    ],
  },
  maxSize = 10 * 1024 * 1024, // 10MB
  className,
}: UploadZoneProps) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      setError(null)
      const selectedFile = acceptedFiles[0]

      if (!selectedFile) return

      if (selectedFile.size > maxSize) {
        setError(`File size exceeds ${maxSize / 1024 / 1024}MB limit`)
        return
      }

      setFile(selectedFile)
    },
    [maxSize]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxFiles: 1,
    maxSize,
  })

  const handleUpload = async () => {
    if (!file) return

    setUploading(true)
    setError(null)

    try {
      await onUpload(file)
      setFile(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setUploading(false)
    }
  }

  const removeFile = () => {
    setFile(null)
    setError(null)
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div
        {...getRootProps()}
        className={cn(
          "border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all",
          isDragActive
            ? "border-primary bg-primary/5 shadow-glow-sm"
            : "border-muted-foreground/25 hover:border-primary/50 hover:bg-primary/[0.02]",
          file && "border-emerald-500 bg-emerald-500/5"
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-2">
          {file ? (
            <>
              <File className="h-10 w-10 text-emerald-500" />
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{file.name}</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeFile()
                  }}
                  className="p-1 hover:bg-muted rounded-lg"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <span className="text-xs text-muted-foreground">
                {(file.size / 1024).toFixed(1)} KB
              </span>
            </>
          ) : (
            <>
              <Upload className="h-10 w-10 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                {isDragActive
                  ? "Drop your resume here"
                  : "Drag and drop your resume, or click to browse"}
              </p>
              <p className="text-xs text-muted-foreground">
                Supports PDF, DOC, DOCX (max {maxSize / 1024 / 1024}MB)
              </p>
            </>
          )}
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive text-center">{error}</p>
      )}

      {file && (
        <Button
          onClick={handleUpload}
          disabled={uploading}
          className="w-full rounded-xl"
        >
          {uploading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Uploading...
            </>
          ) : (
            <>
              <Upload className="mr-2 h-4 w-4" />
              Upload Resume
            </>
          )}
        </Button>
      )}
    </div>
  )
}
