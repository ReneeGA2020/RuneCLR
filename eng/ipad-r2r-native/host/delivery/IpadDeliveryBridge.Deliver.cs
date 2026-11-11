using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using RuneCLR.TrustedUpdate;

namespace RuneCLR.IpadDelivery;

public static partial class IpadDeliveryBridge
{
    /// <summary>
    /// Downloads and publishes one release offer, then re-verifies the SAME final root and applies the
    /// required compatibility gate. The returned candidate is the one the envelope signed; the offer's
    /// VersionName/entry fields are only used as an expected-match check.
    /// </summary>
    public static async ValueTask<DeliveryResult> DeliverAsync(DeliveryOptions options, DeliveryOffer offer,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(offer);
        options.Validate();

        byte[] document;
        try
        {
            document = await BoundedHttpFetch.DownloadAsync(offer.DocumentUri, options.MaxDocumentBytes,
                options.DownloadDeadline, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception error)
        {
            return Fail(DeliveryFailure.DownloadFailed, error.GetType().Name);
        }

        var sources = new TrustedReleaseStageSource[offer.Content.Count];
        for (var i = 0; i < sources.Length; i++)
        {
            var entry = offer.Content[i];
            sources[i] = new TrustedReleaseStageSource(entry.RelativePath,
                token => OpenContent(entry.Uri, options, token));
        }

        TrustedReleaseStageResult staged;
        try
        {
            staged = await TrustedReleaseStaging.PublishAsync(options.FinalReleaseDirectory, document,
                options.HostSubjectPublicKeyInfo, sources, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception error)
        {
            return Fail(DeliveryFailure.StagingFailed, error.GetType().Name);
        }
        if (!staged.Succeeded)
            return Fail(DeliveryFailure.StagingFailed, staged.Failure + ":" + staged.Detail);

        // Same-root re-verification: the candidate used for compatibility and activation is bound to
        // the directory that was just published, not to anything the offer supplied.
        var verified = TrustedRelease.Verify(options.FinalReleaseDirectory, document, options.HostSubjectPublicKeyInfo);
        if (!verified.Succeeded)
            return Fail(DeliveryFailure.VerificationFailed, verified.Failure + ":" + verified.Detail);
        var candidate = verified.Candidate!;

        if (!string.Equals(offer.VersionName, candidate.VersionName, StringComparison.Ordinal))
            return Fail(DeliveryFailure.VerificationFailed, "version-mismatch");
        // P2-2: expected entry fields, when supplied, must match the signed manifest exactly.
        if (offer.EntryAssemblyName.Length > 0 &&
            !string.Equals(offer.EntryAssemblyName, Path.GetFileName(candidate.AssemblyPath), StringComparison.Ordinal))
            return Fail(DeliveryFailure.VerificationFailed, "entry-assembly-mismatch");
        if (offer.EntryTypeName.Length > 0 &&
            !string.Equals(offer.EntryTypeName, candidate.EntryTypeName, StringComparison.Ordinal))
            return Fail(DeliveryFailure.VerificationFailed, "entry-type-mismatch");
        if (offer.EntryMethodName.Length > 0 &&
            !string.Equals(offer.EntryMethodName, candidate.EntryMethodName, StringComparison.Ordinal))
            return Fail(DeliveryFailure.VerificationFailed, "entry-method-mismatch");

        // Same predicate as Start: no parallel/weaker compatibility path in the delivery flow.
        var check = Check(options, options.FinalReleaseDirectory, candidate, out var status, out var detail);
        if (!check)
            return new DeliveryResult(DeliveryFailure.CompatibilityRejected, detail, false, status, candidate.VersionName);

        // P1-2: give the host the exact offer Start needs; the document is a private copy so later
        // mutation of the caller's buffer cannot change what was verified.
        return new DeliveryResult(DeliveryFailure.None, "", false, status, candidate.VersionName)
        {
            Offer = new TrustedReleaseOffer(options.FinalReleaseDirectory, (byte[])document.Clone()),
        };
    }

    private static async ValueTask<Stream> OpenContent(Uri uri, DeliveryOptions options, CancellationToken token)
    {
        var bytes = await BoundedHttpFetch.DownloadAsync(uri, TrustedRelease.MaxFileBytes, options.DownloadDeadline, token)
            .ConfigureAwait(false);
        return new MemoryStream(bytes, writable: false);
    }

    private static DeliveryResult Fail(DeliveryFailure failure, string detail) =>
        new(failure, detail, false, null, null);
}

