package com.pawtrack.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.pawtrack.app.databinding.ActivitySetupBinding

class SetupActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySetupBinding
    private lateinit var prefs: PrefsRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = PrefsRepository(this)

        // Returning user with a server already configured and onboarding
        // already completed — skip straight past setup.
        if (prefs.onboardingDone && !prefs.serverUrl.isNullOrBlank()) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }

        binding = ActivitySetupBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs.serverUrl?.let { binding.urlInput.setText(it) }

        binding.continueButton.setOnClickListener {
            val raw = binding.urlInput.text?.toString()?.trim().orEmpty()
            val normalized = normalizeUrl(raw)
            if (normalized == null) {
                binding.urlInputLayout.error = getString(R.string.setup_url_error)
                return@setOnClickListener
            }
            binding.urlInputLayout.error = null
            prefs.serverUrl = normalized
            startActivity(Intent(this, PermissionsActivity::class.java))
        }
    }

    private fun normalizeUrl(input: String): String? {
        if (input.isBlank()) return null
        val candidate = if (input.startsWith("http://") || input.startsWith("https://")) input else "https://$input"
        val uri = Uri.parse(candidate)
        if (uri.host.isNullOrBlank()) return null
        return candidate.trimEnd('/')
    }
}
